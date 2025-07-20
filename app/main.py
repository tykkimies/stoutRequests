from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request, Depends, status, Query
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBearer
from sqlmodel import Session, select

from .core.database import create_db_and_tables, get_session, engine
from .core.template_context import get_global_template_context
from .services.settings_service import build_app_url
from .api.auth import router as auth_router, get_current_user
from .api.search import router as search_router
from .api.requests import router as requests_router
from .api.admin import router as admin_router
from .api.setup import router as setup_router
from .api.services import router as services_router
from app.api import setup
from .models import User, UserCategoryPreferences
from .services.plex_sync_service import PlexSyncService
from .services.permissions_service import PermissionsService


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    create_db_and_tables()
    
    # Initialize default roles and permissions
    with Session(engine) as session:
        PermissionsService.ensure_default_roles(session)
    
    yield

app = FastAPI(title="Stout Requests", version="1.0.0", lifespan=lifespan)

# Add middleware to handle base_url routing
@app.middleware("http") 
async def base_url_routing_middleware(request: Request, call_next):
    """Handle dynamic base_url routing for reverse proxy support"""
    from .services.settings_service import SettingsService
    
    try:
        # Get the configured base_url (only if settings exist)
        base_url = None
        try:
            with Session(engine) as session:
                if SettingsService.is_configured(session):
                    base_url = SettingsService.get_base_url(session)
        except:
            # Database might not be initialized yet, continue without base_url
            pass
        
        if base_url:
            # Remove leading/trailing slashes for consistency
            base_url = base_url.strip('/')
            request_path = request.url.path
            
            # Debug logging for reverse proxy issues
            print(f"🔍 Base URL middleware: base_url='{base_url}', request_path='{request_path}'")
            print(f"🔍 Full URL: {request.url}")
            print(f"🔍 Headers: {dict(request.headers)}")
            
            # Handle requests under the base_url path
            if request_path.startswith(f'/{base_url}/'):
                # Strip base_url from path for internal routing
                new_path = request_path[len(base_url) + 1:]
                if not new_path.startswith('/'):
                    new_path = '/' + new_path
                
                # Update request scope for internal routing
                request.scope["path"] = new_path
                request.scope["root_path"] = f"/{base_url}"
                print(f"🔧 Stripped base_url: new_path='{new_path}', root_path='{request.scope['root_path']}'")
                
            elif request_path == f'/{base_url}':
                # Handle exact base_url match (redirect to base_url/)
                from fastapi.responses import RedirectResponse
                return RedirectResponse(url=f"/{base_url}/")
                
            elif request_path == f'/{base_url}/':
                # Handle base_url/ -> root
                request.scope["path"] = "/"
                request.scope["root_path"] = f"/{base_url}"
                print(f"🔧 Base URL root: new_path='/', root_path='{request.scope['root_path']}'")
                
            elif not request_path.startswith('/static') and request_path != '/' and not request_path.startswith('/setup'):
                # Check if this might be a reverse proxy stripping the base_url
                # If the Host header shows our domain but path doesn't include base_url,
                # assume reverse proxy stripped it and set root_path accordingly
                host = request.headers.get('host', '')
                if 'duckdns.org' in host or 'plexmanager' in host:
                    print(f"🔧 Reverse proxy detected: Setting root_path for stripped path")
                    request.scope["root_path"] = f"/{base_url}"
                else:
                    # For other requests not under base_url (except static, root, and setup), redirect to base_url
                    print(f"🔧 Redirecting to base_url: /{base_url}{request_path}")
                    from fastapi.responses import RedirectResponse
                    return RedirectResponse(url=f"/{base_url}{request_path}")
    
    except Exception as e:
        # If there's any error, continue without base_url handling
        pass
    
    response = await call_next(request)
    return response

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include API routers
app.include_router(auth_router)
app.include_router(search_router)
app.include_router(requests_router)
app.include_router(admin_router)
app.include_router(setup_router)
app.include_router(services_router)
# app.include_router(setup.router)

# Setup templates
templates = Jinja2Templates(directory="app/templates")

# Security
security = HTTPBearer(auto_error=False)


def create_template_response(template_name: str, context: dict):
    """Create a template response with global context included"""
    current_user = context.get('current_user')
    request = context.get('request')
    global_context = get_global_template_context(current_user, request)
    # Merge contexts, with explicit context taking precedence
    merged_context = {**global_context, **context}
    print(f"🔧 [CREATE_TEMPLATE_RESPONSE] Template: {template_name}")
    print(f"🔧 [CREATE_TEMPLATE_RESPONSE] Global context base_url: '{global_context.get('base_url', 'MISSING')}'")
    print(f"🔧 [CREATE_TEMPLATE_RESPONSE] Final merged context base_url: '{merged_context.get('base_url', 'MISSING')}'")
    return templates.TemplateResponse(template_name, merged_context)


async def get_current_user_optional(
    request: Request,
    session: Session = Depends(get_session)
) -> User | None:
    """Get current user if logged in, otherwise return None"""
    try:
        # Check for authorization header first
        auth_header = request.headers.get("authorization")
        token = None
        
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
            print(f"🔍 Found auth header token: {token[:10]}...")
        else:
            # Check for token in cookies as fallback
            token = request.cookies.get("access_token")
            if token:
                print(f"🔍 Found cookie token: {token[:10]}...")
        
        if not token:
            print("❌ No token found in headers or cookies")
            return None
        
        # Mock credentials for get_current_user
        from fastapi.security import HTTPAuthorizationCredentials
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )
        
        user = await get_current_user(credentials, session)
        print(f"✅ Authentication successful for user: {user.username} (ID: {user.id}, admin: {user.is_admin})")
        return user
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return None




@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request, 
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    # Check if app is configured, redirect to setup if not
    from .services.settings_service import SettingsService
    if not SettingsService.is_configured(session):
        return RedirectResponse(url=build_app_url("/setup"), status_code=302)
    
    # If user is not authenticated, redirect to login
    if not current_user:
        return RedirectResponse(url=build_app_url("/login"), status_code=302)
    
    # Extract query parameters for initial filter state
    query_params = dict(request.query_params)
    
    return create_template_response(
        "index_categories.html", 
        {
            "request": request, 
            "current_user": current_user
        }
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return create_template_response("login.html", {"request": request})


@app.get("/logout")
async def logout():
    response = RedirectResponse(url=build_app_url("/login"), status_code=status.HTTP_302_FOUND)
    # Clear all possible auth cookies
    response.delete_cookie("access_token")
    response.delete_cookie("plex_token")
    response.delete_cookie("session_id")
    return response


@app.get("/test-user-redirect")
async def test_user_redirect(token: str, username: str):
    """Clean redirect for test user login"""
    from fastapi.responses import HTMLResponse
    
    # Get the home URL with base URL prefix
    home_url = build_app_url("/?test_user=true")
    
    # Create a clean redirect page that clears all auth state and sets new token
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Switching to Test User...</title>
        <meta charset="utf-8">
    </head>
    <body>
        <div style="text-align: center; padding: 50px; font-family: Arial, sans-serif;">
            <h2>Switching to test user: {username}</h2>
            <p>Please wait...</p>
            <div style="width: 50px; height: 50px; border: 5px solid #f3f3f3; border-top: 5px solid #3498db; border-radius: 50%; animation: spin 1s linear infinite; margin: 20px auto;"></div>
        </div>
        
        <style>
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        </style>
        
        <script>
        // Clear all localStorage and sessionStorage
        localStorage.clear();
        sessionStorage.clear();
        
        // Clear all cookies
        document.cookie.split(";").forEach(function(c) {{ 
            document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/"); 
        }});
        
        // Set the new test user token
        document.cookie = "access_token={token}; path=/; max-age=1800";
        
        // Redirect to home page after clearing auth state
        setTimeout(function() {{
            window.location.href = "{home_url}";
        }}, 2000);
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


@app.get("/emergency-admin")
async def emergency_admin_login(session: Session = Depends(get_session)):
    """Emergency admin login - bypasses Plex OAuth (for rate limit recovery)"""
    try:
        # Find the first admin user
        admin_statement = select(User).where(User.is_admin == True).order_by(User.id)
        admin_user = session.exec(admin_statement).first()
        
        if not admin_user:
            return HTMLResponse("❌ No admin user found in database", status_code=404)
        
        # Create a token for the admin user
        from .core.auth import create_access_token
        from datetime import timedelta
        
        access_token = create_access_token(
            data={"sub": admin_user.username}, 
            expires_delta=timedelta(hours=2)  # 2 hour token
        )
        
        # Create response and set cookie
        response = RedirectResponse(url=build_app_url("/admin"), status_code=303)
        response.set_cookie(
            key="access_token", 
            value=access_token, 
            httponly=True, 
            max_age=2 * 60 * 60  # 2 hours
        )
        
        return response
        
    except Exception as e:
        return HTMLResponse(f"❌ Emergency login failed: {str(e)}", status_code=500)


@app.get("/unauthorized", response_class=HTMLResponse)
async def unauthorized_page(
    request: Request,
    username: str = "",
    session: Session = Depends(get_session)
):
    """Show unauthorized access page with helpful information"""
    user_info = None
    admin_contact = None
    
    if username:
        # Try to get user info if username provided
        try:
            statement = select(User).where(User.username == username)
            user = session.exec(statement).first()
            if user:
                user_info = {"username": user.username, "full_name": user.full_name}
        except:
            pass
    
    # Try to get admin contact info
    try:
        admin_statement = select(User).where(User.is_admin == True)
        admin = session.exec(admin_statement).first()
        if admin and admin.email:
            admin_contact = f"Contact: {admin.email}"
        elif admin:
            admin_contact = f"Contact: {admin.username} (via Plex)"
    except:
        pass
    
    return create_template_response(
        "unauthorized.html",
        {
            "request": request,
            "user_info": user_info,
            "admin_contact": admin_contact
        }
    )


async def filter_database_category(
    request: Request,
    db_category_type: str, 
    db_category_sort: str,
    media_type: str,
    genres: list[str],
    rating_source: str,
    rating_min: str,
    page: int,
    limit: int,
    current_user,
    session,
    tmdb_service
):
    """Filter database categories (recent requests, recently added) by TMDB criteria"""
    from .services.settings_service import SettingsService
    
    print(f"🔍 Filtering database category: {db_category_type}/{db_category_sort}")
    print(f"🔍 Filters - Media Type: {media_type}, Genres: {genres}, Rating: {rating_min}")
    
    # Get database items first
    database_items = []
    
    if db_category_type == "plex" and db_category_sort == "recently_added":
        # Get recently added from Plex database
        from app.models.plex_library_item import PlexLibraryItem
        from datetime import datetime, timedelta
        
        one_week_ago = datetime.utcnow() - timedelta(days=7)
        recent_statement = select(PlexLibraryItem).where(
            PlexLibraryItem.added_at >= one_week_ago,
            PlexLibraryItem.added_at.is_not(None)
        ).order_by(PlexLibraryItem.added_at.desc()).limit(100)  # Get more to filter from
        
        recent_plex_items = session.exec(recent_statement).all()
        
        for plex_item in recent_plex_items:
            if plex_item.tmdb_id:
                database_items.append({
                    'tmdb_id': plex_item.tmdb_id,
                    'media_type': plex_item.media_type,
                    'title': plex_item.title,
                    'in_plex': True,
                    'status': 'in_plex'
                })
    
    elif db_category_type == "requests" and db_category_sort == "recent":
        # Get recent requests from database
        from app.models.media_request import MediaRequest, RequestStatus
        from app.models.user import User
        
        recent_statement = select(MediaRequest).where(
            MediaRequest.status != RequestStatus.AVAILABLE
        ).order_by(MediaRequest.created_at.desc()).limit(100)  # Get more to filter from
        
        recent_requests = session.exec(recent_statement).all()
        
        for request_item in recent_requests:
            if request_item.tmdb_id:
                database_items.append({
                    'tmdb_id': request_item.tmdb_id,
                    'media_type': request_item.media_type.value if hasattr(request_item.media_type, 'value') else str(request_item.media_type),
                    'title': request_item.title,
                    'in_plex': False,
                    'status': 'available'
                })
    
    # Fetch TMDB details and apply filters
    filtered_results = []
    base_url = SettingsService.get_base_url(session)
    
    for db_item in database_items:
        try:
            # Skip if media type filter doesn't match
            if media_type != "mixed" and db_item['media_type'] != media_type:
                continue
                
            # Fetch TMDB details
            if db_item['media_type'] == 'movie':
                tmdb_data = tmdb_service.get_movie_details(db_item['tmdb_id'])
            else:
                tmdb_data = tmdb_service.get_tv_details(db_item['tmdb_id'])
            
            if not tmdb_data:
                continue
                
            # Apply genre filter
            if genres:
                genre_ids = [int(g) for g in genres]
                item_genre_ids = tmdb_data.get('genre_ids', []) or [g.get('id') for g in tmdb_data.get('genres', [])]
                if not any(genre_id in item_genre_ids for genre_id in genre_ids):
                    continue
            
            # Apply rating filter
            if rating_source == "tmdb" and rating_min:
                min_rating = float(rating_min)
                if tmdb_data.get('vote_average', 0) < min_rating:
                    continue
            
            # Create result item
            item = {
                'id': tmdb_data['id'],
                'title': tmdb_data.get('title'),
                'name': tmdb_data.get('name'),
                'overview': tmdb_data.get('overview', ''),
                'poster_path': tmdb_data.get('poster_path'),
                'poster_url': f"https://image.tmdb.org/t/p/w500{tmdb_data.get('poster_path')}" if tmdb_data.get('poster_path') else None,
                'release_date': tmdb_data.get('release_date', ''),
                'first_air_date': tmdb_data.get('first_air_date', ''),
                'vote_average': tmdb_data.get('vote_average', 0),
                'media_type': db_item['media_type'],
                'in_plex': db_item['in_plex'],
                'status': db_item['status'],
                'base_url': base_url
            }
            
            filtered_results.append(item)
            
        except Exception as e:
            print(f"❌ Error filtering database item {db_item['tmdb_id']}: {e}")
            continue
    
    # Apply pagination
    start_index = (page - 1) * limit
    end_index = start_index + limit
    paginated_results = filtered_results[start_index:end_index]
    
    total_results = len(filtered_results)
    total_pages = (total_results + limit - 1) // limit
    
    print(f"🔍 Database category filtering: {len(database_items)} items -> {len(filtered_results)} filtered -> {len(paginated_results)} paginated")
    
    # Return the same structure as regular discover
    hx_target = request.headers.get("HX-Target", "")
    if request.headers.get("HX-Request"):
        if hx_target == "categories-container":
            return create_template_response(
                "components/expanded_results.html",
                {
                    "request": request,
                    "results": paginated_results,
                    "current_user": current_user,
                    "category_type": media_type,
                    "category_sort": f"{db_category_type}_{db_category_sort}_filtered",
                    "category_title": f"Filtered {db_category_type.title()} {db_category_sort.replace('_', ' ').title()}",
                    "page": page,
                    "total_pages": total_pages,
                    "total_results": total_results,
                    "current_rating_min": rating_min,
                    "current_media_type": media_type,
                    "current_content_sources": [],
                    "current_genres": genres
                }
            )
        elif hx_target == "results-grid":
            return create_template_response(
                "components/movie_cards_only.html",
                {
                    "request": request,
                    "results": paginated_results,
                    "current_user": current_user,
                    "media_type": media_type,
                    "page": page,
                    "total_pages": total_pages,
                    "current_media_type": media_type,
                    "current_content_sources": [],
                    "current_genres": genres,
                    "current_rating_min": rating_min
                }
            )
    
    # Full page response (shouldn't normally happen)
    return create_template_response(
        "discover_results.html",
        {
            "request": request,
            "results": paginated_results,
            "current_user": current_user,
            "media_type": media_type,
            "page": page,
            "total_pages": total_pages,
            "total_results": total_results
        }
    )


@app.get("/discover", response_class=HTMLResponse)
async def discover_page(
    request: Request,
    media_type: str = "movie",
    content_sources: list[str] = Query(default=[]),
    genres: list[str] = Query(default=[]),
    rating_source: str = "",
    rating_min: str = "",
    studios: list[str] = Query(default=[]),
    streaming: list[str] = Query(default=[]),
    page: int = 1,
    limit: int = 40,  # Match expanded view page size
    # Parameters for filtering database categories
    db_category_type: str = Query(default="", description="Type for database categories (plex, requests, recommendations)"),
    db_category_sort: str = Query(default="", description="Sort for database categories (recently_added, recent, personalized)"),
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Discover movies and TV shows with filters"""
    if not current_user:
        from fastapi.responses import HTMLResponse
        return HTMLResponse('<div class="text-center py-8 text-red-600">Please log in to discover content.</div>')
    
    from .services.tmdb_service import TMDBService
    from .services.plex_service import PlexService
    
    tmdb_service = TMDBService(session)
    plex_service = PlexService(session)
    
    try:
        # Handle filtering for database categories (recent requests, recently added, etc.)
        if db_category_type and db_category_sort:
            print(f"🔍 DISCOVER DEBUG - Filtering database category: {db_category_type}/{db_category_sort}")
            return await filter_database_category(
                request, db_category_type, db_category_sort, media_type, 
                genres, rating_source, rating_min, page, limit,
                current_user, session, tmdb_service
            )
        # Convert genres list to comma-separated string for TMDB
        genre_filter = ",".join(genres) if genres else None
        
        # Convert rating to TMDB format
        rating_filter = None
        if rating_source == "tmdb" and rating_min:
            rating_filter = float(rating_min)
        
        # Convert streaming providers to comma-separated string for TMDB
        streaming_filter = ",".join(streaming) if streaming else None
        
        # Check if we should use pure TMDB discover endpoint instead of content sources
        use_discover_endpoint = (
            not content_sources or  # No sources selected
            len(content_sources) == 0
        )
        
        print(f"🔍 DISCOVER DEBUG - Content sources received: {content_sources}")
        print(f"🔍 DISCOVER DEBUG - Use discover endpoint: {use_discover_endpoint}")
        print(f"🔍 DISCOVER DEBUG - Media type: {media_type}")
        print(f"🔍 DISCOVER DEBUG - Genres: {genres}")
        print(f"🔍 DISCOVER DEBUG - Rating filter: {rating_filter}")
        
        all_results = []
        total_pages = 1
        total_results = 0
        
        if use_discover_endpoint:
            print(f"🔍 Using TMDB Discover endpoint (no content sources) - Genres: {genres}, Rating: {rating_filter}")
            
            # Use TMDB discover endpoint with all filters - this searches ALL content, not just popular
            media_types_to_fetch = ["movie", "tv"] if media_type == "mixed" else [media_type]
            
            for target_media_type in media_types_to_fetch:
                try:
                    if target_media_type == "movie":
                        discover_results = tmdb_service.discover_movies(
                            page=page,
                            sort_by="popularity.desc",  # Sort by popularity but search all content
                            with_genres=genre_filter,
                            vote_average_gte=rating_filter,
                            with_watch_providers=streaming_filter,
                        )
                    else:  # tv
                        discover_results = tmdb_service.discover_tv(
                            page=page,
                            sort_by="popularity.desc",  # Sort by popularity but search all content
                            with_genres=genre_filter,
                            vote_average_gte=rating_filter,
                            with_watch_providers=streaming_filter,
                        )
                    
                    # Add media_type and source info to all items
                    for item in discover_results.get('results', []):
                        item['media_type'] = target_media_type
                        item['content_source'] = 'discover_all'  # Indicate this is from discover endpoint
                        all_results.append(item)
                    
                    # Update pagination info
                    total_pages = max(total_pages, discover_results.get('total_pages', 1))
                    total_results += discover_results.get('total_results', 0)
                    
                    print(f"🎯 Discover {target_media_type} returned {len(discover_results.get('results', []))} items from ALL content")
                    
                except Exception as e:
                    print(f"❌ Error using discover endpoint for {target_media_type}: {e}")
                    # Don't fallback to popular - if discover fails, show error
                    continue
        else:
            print(f"🔍 Using traditional content sources: {content_sources}")
            
            # Helper function to fetch from a specific content source
            # Use the same methods as /discover/category for consistency
            def fetch_from_source(source, target_media_type):
                try:
                    # If any filters are applied (genres, rating, streaming), use discover endpoint for consistency
                    has_filters = bool(genre_filter or rating_filter or streaming_filter)
                    
                    if source == "trending":
                        if has_filters:
                            # Use discover endpoint with trending sort when filters are applied
                            if target_media_type == "movie":
                                return tmdb_service.discover_movies(
                                    page=page, sort_by="popularity.desc",  # Closest to trending
                                    with_genres=genre_filter, vote_average_gte=rating_filter,
                                    with_watch_providers=streaming_filter
                                )
                            else:
                                return tmdb_service.discover_tv(
                                    page=page, sort_by="popularity.desc",  # Closest to trending
                                    with_genres=genre_filter, vote_average_gte=rating_filter,
                                    with_watch_providers=streaming_filter
                                )
                        else:
                            # No filters, use trending endpoint for consistency with View All
                            return tmdb_service.get_trending(target_media_type, page)
                    elif source == "popular":
                        if has_filters:
                            # Use discover endpoint with popularity sort when filters are applied
                            if target_media_type == "movie":
                                return tmdb_service.discover_movies(
                                    page=page, sort_by="popularity.desc",
                                    with_genres=genre_filter, vote_average_gte=rating_filter,
                                    with_watch_providers=streaming_filter
                                )
                            else:
                                return tmdb_service.discover_tv(
                                    page=page, sort_by="popularity.desc",
                                    with_genres=genre_filter, vote_average_gte=rating_filter,
                                    with_watch_providers=streaming_filter
                                )
                        else:
                            # No filters, use popular endpoint for consistency with View All
                            return tmdb_service.get_popular(target_media_type, page)
                    elif source == "top_rated":
                        if has_filters:
                            # Use discover endpoint with rating sort when filters are applied
                            if target_media_type == "movie":
                                return tmdb_service.discover_movies(
                                    page=page, sort_by="vote_average.desc",
                                    with_genres=genre_filter, vote_average_gte=rating_filter,
                                    with_watch_providers=streaming_filter
                                )
                            else:
                                return tmdb_service.discover_tv(
                                    page=page, sort_by="vote_average.desc",
                                    with_genres=genre_filter, vote_average_gte=rating_filter,
                                    with_watch_providers=streaming_filter
                                )
                        else:
                            # No filters, use top_rated endpoint for consistency with View All
                            return tmdb_service.get_top_rated(target_media_type, page)
                    elif source == "upcoming" and target_media_type == "movie":
                        return tmdb_service.get_upcoming_movies(page)
                    elif source == "now_playing" and target_media_type == "movie":
                        return tmdb_service.get_now_playing_movies(page)
                    else:
                        return {"results": [], "total_pages": 1, "total_results": 0}
                except Exception as e:
                    print(f"Error fetching from {source}: {e}")
                    return {"results": [], "total_pages": 1, "total_results": 0}
            
            # Determine which media types to fetch
            media_types_to_fetch = ["movie", "tv"] if media_type == "mixed" else [media_type]
            
            # Fetch from each selected content source
            seen_ids = set()  # For deduplication
            
            for source in content_sources:
                for target_media_type in media_types_to_fetch:
                    source_results = fetch_from_source(source, target_media_type)
                    
                    # Add media_type and deduplicate
                    for item in source_results.get('results', []):
                        # Create unique identifier
                        item_id = f"{item.get('id', 0)}_{target_media_type}"
                        
                        if item_id not in seen_ids:
                            seen_ids.add(item_id)
                            item['media_type'] = target_media_type
                            item['content_source'] = source  # Track which source this came from
                            
                            # Apply genre filter for trending/upcoming/now_playing (which don't support server-side filtering)
                            if source in ["trending", "upcoming", "now_playing"] and genre_filter:
                                genre_ids = [int(g) for g in genres]
                                if any(genre_id in item.get('genre_ids', []) for genre_id in genre_ids):
                                    all_results.append(item)
                            elif source not in ["trending", "upcoming", "now_playing"]:
                                # For discover endpoints, genres are already filtered server-side
                                all_results.append(item)
                            elif not genre_filter:
                                # No genre filter, include everything
                                all_results.append(item)
                    
                    # Update pagination info
                    total_pages = max(total_pages, source_results.get('total_pages', 1))
                    total_results += source_results.get('total_results', 0)
        
        # Sort combined results by vote_average * popularity for better mixing
        all_results.sort(key=lambda x: (x.get('vote_average', 0) * 0.3 + x.get('popularity', 0) * 0.7), reverse=True)
        
        # For discover endpoint, return all results from current TMDB page (no artificial pagination)
        # TMDB handles the real pagination with 20 results per page
        results = {
            'results': all_results,
            'total_pages': total_pages,
            'total_results': total_results
        }
        
        print(f"🔍 DISCOVER RESULTS - Page {page}: {len(all_results)} results, Total Pages: {total_pages}, Total Results: {total_results}")
        
        # Note: Genre and TMDB rating filtering is now handled server-side via discover endpoints
        # Only apply client-side filtering for cases where server-side filtering isn't available
        
        # Filter by rating if specified and not handled server-side
        if rating_source and rating_min and results.get('results') and rating_source != 'tmdb':
            min_rating = float(rating_min)
            filtered_results = []
            
            for item in results['results']:
                should_include = False
                
                if rating_source == 'imdb':
                    # For IMDb, we would need to fetch external IDs and ratings
                    # For now, fallback to TMDB rating as approximation
                    tmdb_rating = item.get('vote_average', 0)
                    should_include = tmdb_rating >= min_rating
                elif rating_source == 'rt':
                    # For Rotten Tomatoes, we would need external API integration
                    # For now, convert TMDB 0-10 to RT 0-100 scale as approximation
                    tmdb_rating = item.get('vote_average', 0)
                    rt_approximation = tmdb_rating * 10  # Convert 0-10 to 0-100
                    should_include = rt_approximation >= min_rating
                
                if should_include:
                    filtered_results.append(item)
            
            results['results'] = filtered_results
        
        # Filter by studios if specified (using production companies from TMDB)
        if studios and results.get('results'):
            from .services.tmdb_service import TMDBService
            studio_ids = [int(studio_id) for studio_id in studios]
            filtered_results = []
            
            for item in results['results']:
                try:
                    # Get detailed info to check production companies
                    detailed_info = tmdb_service.get_details(item['id'], media_type)
                    production_companies = detailed_info.get('production_companies', [])
                    
                    # Check if any of the item's production companies match selected studios
                    item_studio_ids = [company.get('id') for company in production_companies]
                    if any(studio_id in item_studio_ids for studio_id in studio_ids):
                        filtered_results.append(item)
                except Exception as e:
                    print(f"Error checking studios for item {item['id']}: {e}")
                    # Include item if we can't check (don't lose content due to API errors)
                    filtered_results.append(item)
            
            results['results'] = filtered_results
        
        # Note: Streaming filters are now handled natively by TMDB via with_watch_providers parameter
        
        # Fast status check using database lookup with fallback
        try:
            sync_service = PlexSyncService(session)
            
            # For mixed content, we need to check each item's media_type individually
            if media_type == "mixed":
                for item in results.get('results', []):
                    item_media_type = item.get('media_type')
                    # Check status for this specific item and media type
                    status_map = sync_service.check_items_status([item['id']], item_media_type)
                    status = status_map.get(item['id'], 'available')
                    item['status'] = status
                    item['in_plex'] = status == 'in_plex'
            else:
                # For single media type, batch check all items
                tmdb_ids = [item['id'] for item in results.get('results', [])]
                status_map = sync_service.check_items_status(tmdb_ids, media_type)
                
                # Add status information to each item
                for item in results.get('results', []):
                    if 'media_type' not in item:
                        item['media_type'] = media_type  # Ensure media_type is set
                    status = status_map.get(item['id'], 'available')
                    item['status'] = status
                    item['in_plex'] = status == 'in_plex'
        except Exception as sync_error:
            print(f"Warning: Fast status check failed, falling back to old method: {sync_error}")
            # Fallback to the old method for now
            for item in results.get('results', []):
                item_media_type = item.get('media_type', media_type)
                if 'media_type' not in item:
                    item['media_type'] = item_media_type
                item['in_plex'] = plex_service.check_media_in_library(item['id'], item_media_type)
                item['status'] = 'in_plex' if item['in_plex'] else 'available'
        
        # Content negotiation - check if this is an HTMX request for fragments
        hx_target = request.headers.get("HX-Target", "")
        print(f"🔍 DISCOVER DEBUG - HX-Request: {request.headers.get('HX-Request')}, HX-Target: '{hx_target}'")
        if request.headers.get("HX-Request"):
            if hx_target in ["discover-results", "content-results", "search-results-content", "filtered-results-content"]:
                # Return only the discover results fragment
                return create_template_response(
                    "discover_results.html",
                    {
                        "request": request, 
                        "results": results.get('results', []),
                        "current_user": current_user,
                        "media_type": media_type,
                        "content_sources": content_sources,
                        "genres": genres,
                        "page": page,
                        "total_pages": results.get('total_pages', 1),
                        "total_results": results.get('total_results', 0)
                    }
                )
            elif hx_target == "results-grid":
                # Return only the media cards for infinite scroll
                return create_template_response(
                    "components/movie_cards_only.html",
                    {
                        "request": request, 
                        "results": results.get('results', []),
                        "current_user": current_user,
                        "media_type": media_type,
                        "page": page,
                        "total_pages": results.get('total_pages', 1),
                        "current_media_type": media_type,
                        "current_content_sources": content_sources,
                        "current_genres": genres,
                        "current_rating_min": rating_min
                    }
                )
            elif hx_target == "categories-container":
                # Return expanded category view (filtered) for categories container
                print(f"🔍 DISCOVER DEBUG - Returning expanded category view for categories-container")
                return create_template_response(
                    "components/expanded_results.html",
                    {
                        "request": request, 
                        "results": results.get('results', []),
                        "current_user": current_user,
                        "category_type": media_type,
                        "category_sort": content_sources[0] if content_sources else 'popular',
                        "category_title": f"Filtered {media_type.title()}s",
                        "page": page,
                        "total_pages": results.get('total_pages', 1),
                        "total_results": results.get('total_results', 0),
                        "current_rating_min": rating_min,
                        "current_media_type": media_type,
                        "current_content_sources": content_sources,
                        "current_genres": genres
                    }
                )
            elif hx_target == "#main-content-area":
                # Return full filtered results view for main content area replacement
                print(f"🔍 DISCOVER DEBUG - Returning discover_filtered_view.html for main-content-area")
                return create_template_response(
                    "discover_filtered_view.html",
                    {
                        "request": request, 
                        "results": results.get('results', []),
                        "current_user": current_user,
                        "media_type": media_type,
                        "content_sources": content_sources,
                        "genres": genres,
                        "page": page,
                        "total_pages": results.get('total_pages', 1),
                        "total_results": results.get('total_results', 0),
                        "current_rating_min": rating_min,
                        "current_media_type": media_type,
                        "current_content_sources": content_sources,
                        "current_genres": genres
                    }
                )
        else:
            # For full page requests or API clients, return full context or JSON
            if request.headers.get("Accept") == "application/json":
                # API response
                return {
                    "success": True,
                    "data": {
                        "results": results.get('results', []),
                        "page": page,
                        "total_pages": results.get('total_pages', 1),
                        "total_results": results.get('total_results', 0),
                        "media_type": media_type,
                        "content_sources": content_sources,
                        "genres": genres
                    }
                }
            else:
                # Full page response - redirect to index with filter params
                from fastapi.responses import RedirectResponse
                import urllib.parse
                
                # Build query parameters for the filters
                params = []
                if media_type != "movie":
                    params.append(f"media_type={media_type}")
                if content_sources:
                    for source in content_sources:
                        params.append(f"content_sources={urllib.parse.quote(source)}")
                if genres:
                    for genre in genres:
                        params.append(f"genres={urllib.parse.quote(genre)}")
                if rating_source:
                    params.append(f"rating_source={urllib.parse.quote(rating_source)}")
                if rating_min:
                    params.append(f"rating_min={urllib.parse.quote(rating_min)}")
                if studios:
                    for studio in studios:
                        params.append(f"studios={urllib.parse.quote(studio)}")
                if streaming:
                    for provider in streaming:
                        params.append(f"streaming={urllib.parse.quote(provider)}")
                if page > 1:
                    params.append(f"page={page}")
                
                query_string = "&".join(params)
                redirect_url = build_app_url("/") + ("?" + query_string if query_string else "")
                return RedirectResponse(url=redirect_url, status_code=302)
        
    except Exception as e:
        print(f"Error in discover: {e}")
        return HTMLResponse(f'<div class="text-center py-8 text-red-600">Error loading content: {str(e)}</div>')



@app.get("/discover/category", response_class=HTMLResponse)
async def discover_category(
    request: Request,
    type: str = "movie",
    sort: str = "trending",
    limit: int = 20,
    offset: int = 0,
    page: int = 1,
    view: str = "horizontal",
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    
    """Get content for a specific category (horizontal scroll)"""
    print(f"🔍 Category request - User: {current_user.username if current_user else 'None'}, Type: {type}, Sort: {sort}")
    
    if not current_user:
        print("❌ No current user found in category request")
        return HTMLResponse('''
            <div class="text-center py-8">
                <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                    <svg class="w-8 h-8 text-yellow-400 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.464 0L4.35 16.5c-.77.833.192 2.5 1.732 2.5z"></path>
                    </svg>
                    <h3 class="text-sm font-medium text-yellow-800 mb-1">Authentication Required</h3>
                    <p class="text-xs text-yellow-700 mb-3">Please log in to view this content</p>
                    <button onclick="window.location.href='{build_app_url("/login")}'" class="text-xs bg-yellow-600 text-white px-3 py-1 rounded hover:bg-yellow-700">
                        Login
                    </button>
                </div>
            </div>
        ''')
    
    from .services.tmdb_service import TMDBService
    from .services.plex_service import PlexService
    from .services.settings_service import SettingsService
        
    base_url = SettingsService.get_base_url(session)
    tmdb_service = TMDBService(session)
    plex_service = PlexService(session)
    
    try:
        # Initialize default values for all category types
        has_more = False
        recently_added = []
        recent_items = []
        limited_results = []
        
        # Handle Plex recently added from database using actual Plex added_at timestamps
        if type == "plex" and sort == "recently_added":
            print(f"🔍 Fetching recently added from database for user: {current_user.username}")
            
            try:
                # Get recently added from database using actual Plex added_at timestamps (past week only)
                from app.models.plex_library_item import PlexLibraryItem
                from datetime import datetime, timedelta
                
                one_week_ago = datetime.utcnow() - timedelta(days=7)
                recent_statement = select(PlexLibraryItem).where(
                    PlexLibraryItem.added_at >= one_week_ago,
                    PlexLibraryItem.added_at.is_not(None)  # Only items with valid added_at timestamps
                ).order_by(
                    PlexLibraryItem.added_at.desc()
                ).offset(offset).limit(limit)
                
                recent_plex_items = session.exec(recent_statement).all()
                print(f"🔍 Found {len(recent_plex_items)} recently added items in database (past week)")
                
                # Check if there are more items for pagination
                count_statement = select(PlexLibraryItem).where(
                    PlexLibraryItem.added_at >= one_week_ago,
                    PlexLibraryItem.added_at.is_not(None)
                )
                total_count = len(session.exec(count_statement).all())
                has_more = (offset + len(recent_plex_items)) < total_count
                
                recently_added = []
                for plex_item in recent_plex_items:
                    if plex_item.tmdb_id:
                        # Use database info first, only fetch TMDB for missing posters
                        item = {
                            'id': plex_item.tmdb_id,
                            'title': plex_item.title if plex_item.media_type == 'movie' else None,
                            'name': plex_item.title if plex_item.media_type == 'tv' else None,
                            'overview': 'Recently added to your Plex server',
                            'poster_path': None,
                            'poster_url': None,
                            'release_date': str(plex_item.year) if plex_item.year else '',
                            'first_air_date': str(plex_item.year) if plex_item.year else '',
                            'vote_average': 0,
                            'media_type': plex_item.media_type,
                            'in_plex': True,
                            'status': 'in_plex',
                            "base_url": base_url,
                        }
                        
                        # Get full TMDB data for poster/details
                        try:
                            if plex_item.media_type == 'movie':
                                tmdb_data = tmdb_service.get_movie_details(plex_item.tmdb_id)
                            else:
                                tmdb_data = tmdb_service.get_tv_details(plex_item.tmdb_id)
                            
                            # Only update if we got good data
                            if tmdb_data:
                                item.update({
                                    'title': tmdb_data.get('title') if plex_item.media_type == 'movie' else item['title'],
                                    'name': tmdb_data.get('name') if plex_item.media_type == 'tv' else item['name'],
                                    'overview': tmdb_data.get('overview', item['overview']),
                                    'poster_path': tmdb_data.get('poster_path'),
                                    'poster_url': f"{tmdb_service.image_base_url}{tmdb_data['poster_path']}" if tmdb_data.get('poster_path') else None,
                                    'release_date': tmdb_data.get('release_date', item['release_date']),
                                    'first_air_date': tmdb_data.get('first_air_date', item['first_air_date']),
                                    'vote_average': tmdb_data.get('vote_average', 0),
                                    "base_url": base_url,
                                })
                                
                        except Exception as tmdb_error:
                            print(f"⚠️ TMDB lookup failed for {plex_item.title}: {tmdb_error}")
                            # Continue with database info
                        
                        print(f"📊 Added Plex item: {item['title'] or item['name']} ({item['media_type']}) - Status: {item['status']}, In Plex: {item['in_plex']}")
                        recently_added.append(item)
                
                if not recently_added:
                    debug_info = f"""
                    <div class="text-center py-8">
                        <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
                            <h3 class="text-yellow-800 font-medium mb-2">🔍 Recently Added to Plex</h3>
                            <div class="text-left text-sm text-yellow-700">
                                <p><strong>Database Items:</strong> {len(recent_plex_items)}</p>
                                <p><strong>Items with TMDB ID:</strong> {len(recently_added)}</p>
                            </div>
                        </div>
                        <p class="text-gray-500">No content added to Plex in the past week.</p>
                        <p class="text-sm text-gray-400 mt-2">Try running a library sync in Admin → Library to update timestamps!</p>
                    </div>
                    """
                    return HTMLResponse(content=debug_info)
                
                print(f"✅ Returning {len(recently_added)} recently added items from database (offset: {offset}, has_more: {has_more})")
                
            except Exception as db_error:
                print(f"❌ Database lookup failed: {db_error}")
                return HTMLResponse(f'<div class="text-center py-8 text-red-600">Error loading recent items: {str(db_error)}</div>')
            
            # Choose template based on view type
            if view == "grid":
                template_name = "discover_results.html"
            elif view == "more":
                template_name = "components/movie_cards_only.html"
            elif view == "expanded":
                template_name = "components/expanded_results.html"
            else:
                template_name = "category_horizontal.html"
            
            return create_template_response(
                template_name,
                {
                    "request": request, 
                    "results": recently_added,
                    "current_user": current_user,
                    "media_type": "mixed",  # Mixed content type
                    "sort_by": sort,
                    "has_more": has_more,
                    "next_offset": offset + limit,
                    "current_offset": offset
                }
            )
        
        # Handle Recent Requests from database
        elif type == "requests" and sort == "recent":
            try:
                from app.models.media_request import MediaRequest
                from app.models.user import User
                from app.services.settings_service import SettingsService
                from .core.permissions import is_user_admin
                
                # Get visibility settings and user admin status
                visibility_config = SettingsService.get_request_visibility_config(session)
                user_is_admin = is_user_admin(current_user, session)
                
                # Import the status enum to filter properly
                from app.models.media_request import RequestStatus
                
                # Build optimized query with joins - exclude fulfilled requests
                # Limit: 20 for horizontal scroll, 40 max for expanded view
                max_limit = min(limit, 40)  # Cap at 40 for expanded view, 20 for horizontal
                
                if user_is_admin or visibility_config['can_view_all_requests']:
                    # Show all recent requests (excluding fulfilled ones) with user join
                    recent_statement = select(MediaRequest, User).outerjoin(
                        User, MediaRequest.user_id == User.id
                    ).where(
                        MediaRequest.status != RequestStatus.AVAILABLE  # Exclude items already in Plex
                    ).order_by(MediaRequest.created_at.desc()).limit(max_limit)
                else:
                    # Show only user's own requests (excluding fulfilled ones)
                    recent_statement = select(MediaRequest, User).outerjoin(
                        User, MediaRequest.user_id == User.id
                    ).where(
                        MediaRequest.user_id == current_user.id,
                        MediaRequest.status != RequestStatus.AVAILABLE  # Exclude items already in Plex
                    ).order_by(MediaRequest.created_at.desc()).limit(max_limit)
                
                recent_results = session.exec(recent_statement).all()
                
                # Prepare batch TMDB requests for better performance
                movie_ids = []
                tv_ids = []
                request_mapping = {}
                
                # First pass: collect TMDB IDs and build mapping
                for result in recent_results:
                    request_item = result[0]  # MediaRequest
                    user = result[1] if len(result) > 1 else None  # User from join
                    
                    if request_item.tmdb_id:
                        media_type_str = request_item.media_type.value if hasattr(request_item.media_type, 'value') else str(request_item.media_type)
                        
                        if media_type_str == 'movie':
                            movie_ids.append(request_item.tmdb_id)
                        else:
                            tv_ids.append(request_item.tmdb_id)
                            
                        request_mapping[request_item.tmdb_id] = {
                            'request': request_item,
                            'user': user,
                            'media_type': media_type_str
                        }
                
                # Batch fetch TMDB data (if possible) or fall back to individual calls
                recent_items = []
                for tmdb_id, data in request_mapping.items():
                    request_item = data['request']
                    user = data['user']
                    media_type_str = data['media_type']
                    
                    try:
                        # Get TMDB data
                        if media_type_str == 'movie':
                            tmdb_data = tmdb_service.get_movie_details(tmdb_id)
                        else:
                            tmdb_data = tmdb_service.get_tv_details(tmdb_id)
                        
                        # Handle status mapping
                        raw_status = request_item.status.value.lower() if hasattr(request_item.status, 'value') else str(request_item.status).lower()
                        request_status = 'in_plex' if raw_status == 'available' else f'requested_{raw_status}'
                        
                        # Determine user visibility
                        visible_user = None
                        if user_is_admin or visibility_config['can_view_request_user']:
                            visible_user = user
                        elif request_item.user_id == current_user.id:
                            visible_user = current_user
                        
                        # Format item for template
                        item = {
                            'id': tmdb_id,
                            'title': tmdb_data.get('title') if media_type_str == 'movie' else None,
                            'name': tmdb_data.get('name') if media_type_str == 'tv' else None,
                            'overview': tmdb_data.get('overview', ''),
                            'poster_path': tmdb_data.get('poster_path'),
                            'poster_url': f"{tmdb_service.image_base_url}{tmdb_data['poster_path']}" if tmdb_data.get('poster_path') else None,
                            'backdrop_path': tmdb_data.get('backdrop_path'),
                            'backdrop_url': f"{tmdb_service.image_base_url}{tmdb_data['backdrop_path']}" if tmdb_data.get('backdrop_path') else None,
                            'release_date': tmdb_data.get('release_date'),
                            'first_air_date': tmdb_data.get('first_air_date'),
                            'vote_average': tmdb_data.get('vote_average', 0),
                            'media_type': media_type_str,
                            'in_plex': request_status == 'in_plex',
                            'status': request_status,
                            'user': visible_user,
                            'created_at': request_item.created_at,
                            'request_id': request_item.id,
                            "base_url": base_url,
                        }
                        recent_items.append(item)
                        
                    except Exception as tmdb_error:
                        # Use basic info from request item if TMDB fails
                        raw_status = request_item.status.value.lower() if hasattr(request_item.status, 'value') else str(request_item.status).lower()
                        request_status = 'in_plex' if raw_status == 'available' else f'requested_{raw_status}'
                        
                        # Determine user visibility  
                        visible_user = None
                        if user_is_admin or visibility_config['can_view_request_user']:
                            visible_user = user
                        elif request_item.user_id == current_user.id:
                            visible_user = current_user
                        
                        item = {
                            'id': tmdb_id,
                            'title': request_item.title if media_type_str == 'movie' else None,
                            'name': request_item.title if media_type_str == 'tv' else None,
                            'overview': request_item.overview or 'Recently requested',
                            'poster_path': request_item.poster_path,
                            'poster_url': None,
                            'backdrop_path': None,
                            'backdrop_url': None,
                            'release_date': request_item.release_date or '',
                            'first_air_date': request_item.release_date or '',
                            'vote_average': 0,
                            'media_type': media_type_str,
                            'in_plex': request_status == 'in_plex',
                            'status': request_status,
                            'user': visible_user,
                            'created_at': request_item.created_at,
                            'request_id': request_item.id,
                            "base_url": base_url,
                        }
                        recent_items.append(item)
                
                if not recent_items:
                    return HTMLResponse("""
                    <div class="text-center py-8">
                        <svg class="w-16 h-16 mx-auto mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
                        </svg>
                        <h3 class="text-lg font-medium text-gray-900 mb-2">No recent requests</h3>
                        <p class="text-gray-500">No requests have been made recently.</p>
                    </div>
                    """)
                
                # Recent requests show all items at once (max 20) - no pagination needed
                has_more = False
                
            except Exception as db_error:
                return HTMLResponse(f'<div class="text-center py-8 text-red-600">Error loading recent requests: {str(db_error)}</div>')
            
            # Check if this is a nested request for expanded content
            hx_target = request.headers.get('HX-Target', '')
            
            # Choose template based on view type - use special template for recent requests
            if view == "expanded" and "expanded-category-content" not in hx_target:
                # For expanded view (initial load), wrap in the expanded category template
                return create_template_response(
                    "components/expanded_category_view.html",
                    {
                        "request": request,
                        "current_user": current_user,
                        "category_title": "📋 Recent Requests",
                        "category_type": "requests",
                        "category_sort": "recent"
                    }
                )
            elif view == "expanded":
                # For expanded content (infinite scroll), use grid template
                template_name = "recent_requests_expanded.html"
            elif view == "grid":
                # For grid view of requests, also use the expanded template
                template_name = "recent_requests_expanded.html"
            else:
                template_name = "recent_requests_horizontal.html"  # Use Jellyseerr-style cards for recent requests
            
            return create_template_response(
                template_name,
                {
                    "request": request, 
                    "results": recent_items,
                    "current_user": current_user,
                    "user_is_admin": user_is_admin,
                    "show_request_user": user_is_admin or visibility_config['can_view_request_user'],
                    "can_view_all_requests": user_is_admin or visibility_config['can_view_all_requests'],
                    "media_type": "mixed",  # Mixed content type
                    "sort_by": sort,
                    "has_more": has_more,  # Always False - show all items at once (max 20)
                    "next_offset": 0,
                    "current_offset": 0
                }
            )
        
        # Handle Personalized Recommendations based on user's request history
        elif type == "recommendations" and sort == "personalized":
            print(f"🎯 Fetching personalized recommendations for user: {current_user.username}")
            
            try:
                # Get user's recent requests to base recommendations on
                from app.models.media_request import MediaRequest
                from datetime import datetime, timedelta
                
                # Look at requests from the past 6 months for better recommendations
                six_months_ago = datetime.utcnow() - timedelta(days=180)
                user_requests_statement = select(MediaRequest).where(
                    MediaRequest.user_id == current_user.id,
                    MediaRequest.created_at >= six_months_ago
                ).order_by(MediaRequest.created_at.desc()).limit(20)  # Use last 20 requests
                
                user_requests = session.exec(user_requests_statement).all()
                print(f"📊 Found {len(user_requests)} recent requests for recommendations")
                
                if not user_requests:
                    # No request history, fall back to popular content
                    print("📊 No request history, falling back to popular content")
                    fallback_results = tmdb_service.get_popular("movie", 1)
                    fallback_tv = tmdb_service.get_popular("tv", 1)
                    
                    all_results = []
                    for item in fallback_results.get('results', [])[:10]:
                        item['media_type'] = 'movie'
                        item['recommendation_reason'] = 'Popular content'
                        all_results.append(item)
                    
                    for item in fallback_tv.get('results', [])[:10]:
                        item['media_type'] = 'tv'
                        item['recommendation_reason'] = 'Popular content'
                        all_results.append(item)
                    
                    has_more = False
                else:
                    # Generate recommendations based on user's request history
                    recommendation_items = []
                    seen_ids = set()
                    
                    for user_request in user_requests[:10]:  # Use top 10 requests for recommendations
                        try:
                            # Handle enum values safely
                            request_media_type = user_request.media_type.value if hasattr(user_request.media_type, 'value') else str(user_request.media_type)
                            
                            # Get similar and recommended items
                            if request_media_type == 'movie':
                                similar_results = tmdb_service.get_movie_similar(user_request.tmdb_id, 1)
                                rec_results = tmdb_service.get_movie_recommendations(user_request.tmdb_id, 1)
                            else:
                                similar_results = tmdb_service.get_tv_similar(user_request.tmdb_id, 1)
                                rec_results = tmdb_service.get_tv_recommendations(user_request.tmdb_id, 1)
                            
                            # Add similar items
                            for item in similar_results.get('results', [])[:3]:  # Top 3 similar
                                item_id = f"{item['id']}_{request_media_type}"
                                if item_id not in seen_ids:
                                    seen_ids.add(item_id)
                                    item['media_type'] = request_media_type
                                    item['recommendation_reason'] = f"Similar to {user_request.title}"
                                    recommendation_items.append(item)
                            
                            # Add recommended items
                            for item in rec_results.get('results', [])[:2]:  # Top 2 recommendations
                                item_id = f"{item['id']}_{request_media_type}"
                                if item_id not in seen_ids:
                                    seen_ids.add(item_id)
                                    item['media_type'] = request_media_type
                                    item['recommendation_reason'] = f"Recommended for {user_request.title}"
                                    recommendation_items.append(item)
                        
                        except Exception as rec_error:
                            print(f"⚠️ Error getting recommendations for {user_request.title}: {rec_error}")
                            continue
                    
                    # Sort by popularity and limit results
                    recommendation_items.sort(key=lambda x: x.get('popularity', 0), reverse=True)
                    
                    # Apply pagination
                    start_idx = offset
                    end_idx = offset + limit
                    all_results = recommendation_items[start_idx:end_idx]
                    
                    has_more = end_idx < len(recommendation_items)
                    print(f"📊 Generated {len(recommendation_items)} total recommendations, returning {len(all_results)}")
                
                # Add Plex status to all recommendations
                movie_ids = [item['id'] for item in all_results if item.get('media_type') == 'movie']
                tv_ids = [item['id'] for item in all_results if item.get('media_type') == 'tv']
                
                sync_service = PlexSyncService(session)
                movie_status = sync_service.check_items_status(movie_ids, 'movie') if movie_ids else {}
                tv_status = sync_service.check_items_status(tv_ids, 'tv') if tv_ids else {}
                
                for item in all_results:
                    if item.get('media_type') == 'movie':
                        status = movie_status.get(item['id'], 'available')
                    else:
                        status = tv_status.get(item['id'], 'available')
                    
                    item['status'] = status
                    item['in_plex'] = status == 'in_plex'
                    
                    # Add poster URL
                    if item.get('poster_path'):
                        item['poster_url'] = f"{tmdb_service.image_base_url}{item['poster_path']}"
                
                # Choose template based on view type
                if view == "grid":
                    template_name = "discover_results.html"
                elif view == "more":
                    template_name = "components/movie_cards_only.html"
                elif view == "expanded":
                    template_name = "components/expanded_results.html"
                else:
                    template_name = "category_horizontal.html"
                
                return create_template_response(
                    template_name,
                    {
                        "request": request, 
                        "results": all_results,
                        "current_user": current_user,
                        "media_type": "mixed",  # Mixed content type
                        "sort_by": sort,
                        "has_more": has_more,
                        "next_offset": offset + limit,
                        "current_offset": offset
                    }
                )
                
            except Exception as rec_error:
                print(f"❌ Error generating personalized recommendations: {rec_error}")
                import traceback
                traceback.print_exc()
                return HTMLResponse('<div class="text-center py-8 text-red-600">Error loading personalized recommendations</div>')
        
        # Handle TMDB categories with enhanced pagination
        # TMDB provides 20 items per page, we need to fetch multiple pages if needed
        if page > 1:
            # Use page parameter directly (for infinite scroll)
            start_page = page
            end_page = page
            print(f"📊 Page-based Pagination - Page: {page}, Limit: {limit}")
        else:
            # Use offset-based calculation (for backwards compatibility)
            items_needed = offset + limit
            start_page = (offset // 20) + 1
            end_page = ((offset + limit - 1) // 20) + 1
            print(f"📊 Offset-based Pagination - Offset: {offset}, Limit: {limit}, Start Page: {start_page}, End Page: {end_page}")
        
        # Fetch multiple pages if needed
        all_results = []
        total_pages = 1
        total_results = 0
        
        for page_num in range(start_page, min(end_page + 1, 26)):  # TMDB usually limits to 25 pages (500 results)
            try:
                if sort == "trending":
                    page_results = tmdb_service.get_trending(type, page_num)
                elif sort == "popular":
                    page_results = tmdb_service.get_popular(type, page_num)
                elif sort == "top_rated":
                    page_results = tmdb_service.get_top_rated(type, page_num)
                elif sort == "upcoming" and type == "movie":
                    page_results = tmdb_service.get_upcoming_movies(page_num)
                elif sort == "now_playing" and type == "movie":
                    page_results = tmdb_service.get_now_playing_movies(page_num)
                else:
                    page_results = tmdb_service.get_popular(type, page_num)
                
                page_items = page_results.get('results', [])
                all_results.extend(page_items)
                
                # Update totals from first page
                if page_num == start_page:
                    total_pages = page_results.get('total_pages', 1)
                    total_results = page_results.get('total_results', 0)
                
                # If we got fewer items than expected, we've reached the end
                if len(page_items) < 20:
                    break
                    
            except Exception as page_error:
                print(f"Error fetching page {page_num}: {page_error}")
                break
        
        # Extract the requested slice
        if page > 1:
            # For page-based requests, return all results from this page
            limited_results = all_results
            # Has more if we got a full page of results and we're not at the limit
            has_more = len(all_results) >= 20 and page < min(total_pages, 25)
        else:
            # For offset-based requests (backwards compatibility)
            start_idx = offset % len(all_results) if all_results else 0
            limited_results = all_results[start_idx:start_idx + limit] if all_results else []
            # Determine if there are more items available
            max_tmdb_results = min(total_results, 500)  # TMDB effective limit
            has_more = (offset + len(limited_results)) < max_tmdb_results and len(limited_results) == limit
        
        max_tmdb_results = min(total_results, 500) if page <= 1 else total_results  # TMDB effective limit
        print(f"📊 Enhanced Pagination Results - Found: {len(all_results)}, Returning: {len(limited_results)}, Has More: {has_more}, Mode: {'page' if page > 1 else 'offset'}")
        
        # Fast status check using database lookup with fallback
        try:
            print(f"🔍 Creating PlexSyncService for user: {current_user.username if current_user else 'None'}")
            sync_service = PlexSyncService(session)
            tmdb_ids = [item['id'] for item in limited_results]
            status_map = sync_service.check_items_status(tmdb_ids, type)
            
            # Add status information to each item
            for item in limited_results:
                item['media_type'] = type  # Ensure media_type is set
                status = status_map.get(item['id'], 'available')
                item['status'] = status
                item['in_plex'] = status == 'in_plex'
        except Exception as sync_error:
            print(f"Warning: Fast status check failed, falling back to old method: {sync_error}")
            # Fallback to the old method for now
            for item in limited_results:
                item['media_type'] = type
                item['in_plex'] = plex_service.check_media_in_library(item['id'], type)
                item['status'] = 'in_plex' if item['in_plex'] else 'available'
        
        # Choose template based on view type
        if view == "grid":
            template_name = "discover_results.html"
        elif view == "more":
            template_name = "components/movie_cards_only.html"
        elif view == "expanded":
            template_name = "components/expanded_results.html"
        else:
            template_name = "category_horizontal.html"
        
        return create_template_response(
            template_name,
            {
                "request": request, 
                "results": limited_results,
                "current_user": current_user,
                "media_type": type,
                "sort_by": sort,
                "page": page,
                "total_pages": total_pages,
                "has_more": has_more,
                "next_offset": offset + limit,
                "current_offset": offset
            }
        )
        
    except Exception as e:
        print(f"Error in discover category: {e}")
        return HTMLResponse(f'<div class="text-center py-8 text-red-600">Error loading content: {str(e)}</div>')


def get_default_categories():
    """Get the default categories available for all users"""
    return [
        {
            'id': 'recently-added',
            'title': '📁 Recently Added to Plex',
            'type': 'plex',
            'sort': 'recently_added',
            'color': 'green',
            'order': 1
        },
        {
            'id': 'recent-requests', 
            'title': '📋 Recent Requests',
            'type': 'requests',
            'sort': 'recent',
            'color': 'purple',
            'order': 2
        },
        {
            'id': 'trending-movies',
            'title': '🔥 Trending Movies', 
            'type': 'movie',
            'sort': 'trending',
            'color': 'red',
            'order': 3
        },
        {
            'id': 'popular-movies',
            'title': '⭐ Popular Movies',
            'type': 'movie', 
            'sort': 'popular',
            'color': 'yellow',
            'order': 4
        },
        {
            'id': 'trending-tv',
            'title': '🔥 Trending TV Shows',
            'type': 'tv',
            'sort': 'trending', 
            'color': 'purple',
            'order': 5
        },
        {
            'id': 'popular-tv',
            'title': '⭐ Popular TV Shows',
            'type': 'tv',
            'sort': 'popular',
            'color': 'indigo', 
            'order': 6
        },
        # Additional categories that users can enable
        {
            'id': 'top-rated-movies',
            'title': '🏆 Top Rated Movies',
            'type': 'movie',
            'sort': 'top_rated',
            'color': 'orange',
            'order': 7
        },
        {
            'id': 'upcoming-movies',
            'title': '🗓️ Upcoming Movies',
            'type': 'movie',
            'sort': 'upcoming',
            'color': 'blue',
            'order': 8
        },
        {
            'id': 'top-rated-tv',
            'title': '🏆 Top Rated TV Shows',
            'type': 'tv',
            'sort': 'top_rated',
            'color': 'emerald',
            'order': 9
        }
    ]


def get_user_categories(user_id: int, session: Session):
    """Get user's customized categories with their preferences applied"""
    default_categories = get_default_categories()
    
    # Get user's category preferences
    stmt = select(UserCategoryPreferences).where(UserCategoryPreferences.user_id == user_id)
    user_prefs = session.exec(stmt).all()
    
    # Create a lookup for user preferences
    prefs_dict = {pref.category_id: pref for pref in user_prefs}
    
    # Apply user customizations to default categories
    customized_categories = []
    for category in default_categories:
        cat_id = category['id']
        user_pref = prefs_dict.get(cat_id)
        
        # If user has a preference for this category
        if user_pref:
            # Skip if user has hidden this category
            if not user_pref.is_visible:
                continue
            # Use user's custom order
            category['order'] = user_pref.display_order
        else:
            # For default categories (first 6), show by default
            # For additional categories (7+), hide by default unless user explicitly enabled
            if category['order'] > 6:
                continue
        
        customized_categories.append(category)
    
    # Sort by display order
    customized_categories.sort(key=lambda x: x['order'])
    
    return customized_categories


@app.get("/discover/categories", response_class=HTMLResponse)
async def discover_categories(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Get categories list for discover page with user customizations"""
    if not current_user:
        return HTMLResponse('<div class="text-center py-8 text-red-600">Please log in to view categories.</div>')
    
    # Get user's customized categories
    categories = get_user_categories(current_user.id, session)
    
    return create_template_response(
        "components/categories_list.html",
        {
            "request": request,
            "current_user": current_user,
            "categories": categories
        }
    )


@app.post("/discover/categories/customize", response_class=HTMLResponse)
async def customize_user_categories(
    request: Request,
    current_user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Update user's category preferences"""
    if not current_user:
        return HTMLResponse('<div class="text-center py-4 text-red-600">Please log in to customize categories.</div>')
    
    # Get form data
    form = await request.form()
    
    # Parse the category preferences from form data
    # Expected format: category_id_visible, category_id_order
    category_updates = {}
    
    for key, value in form.items():
        if key.endswith('_visible'):
            cat_id = key.replace('_visible', '')
            if cat_id not in category_updates:
                category_updates[cat_id] = {'visible': False, 'order': 0}
            category_updates[cat_id]['visible'] = value == 'on'
        elif key.endswith('_order'):
            cat_id = key.replace('_order', '')
            if cat_id not in category_updates:
                category_updates[cat_id] = {'visible': False, 'order': 0}
            try:
                category_updates[cat_id]['order'] = int(value)
            except (ValueError, TypeError):
                category_updates[cat_id]['order'] = 0
    
    # Update database with new preferences
    for cat_id, prefs in category_updates.items():
        # Check if preference exists
        stmt = select(UserCategoryPreferences).where(
            UserCategoryPreferences.user_id == current_user.id,
            UserCategoryPreferences.category_id == cat_id
        )
        existing_pref = session.exec(stmt).first()
        
        if existing_pref:
            # Update existing preference
            existing_pref.is_visible = prefs['visible']
            existing_pref.display_order = prefs['order']
            existing_pref.updated_at = datetime.utcnow()
        else:
            # Create new preference
            new_pref = UserCategoryPreferences(
                user_id=current_user.id,
                category_id=cat_id,
                is_visible=prefs['visible'],
                display_order=prefs['order']
            )
            session.add(new_pref)
    
    session.commit()
    
    # Return success message
    return HTMLResponse('<div class="text-center py-4 text-green-600">Categories updated successfully!</div>')


@app.get("/discover/categories/settings", response_class=HTMLResponse)
async def category_settings_page(
    request: Request,
    current_user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Show category customization settings page"""
    if not current_user:
        return HTMLResponse('<div class="text-center py-8 text-red-600">Please log in to customize categories.</div>')
    
    # Get all available categories
    all_categories = get_default_categories()
    
    # Get user's current preferences
    stmt = select(UserCategoryPreferences).where(UserCategoryPreferences.user_id == current_user.id)
    user_prefs = session.exec(stmt).all()
    prefs_dict = {pref.category_id: pref for pref in user_prefs}
    
    # Apply user preferences to categories
    for category in all_categories:
        cat_id = category['id']
        user_pref = prefs_dict.get(cat_id)
        
        if user_pref:
            category['user_visible'] = user_pref.is_visible
            category['user_order'] = user_pref.display_order
        else:
            # Default visibility (first 6 categories visible, rest hidden)
            category['user_visible'] = category['order'] <= 6
            category['user_order'] = category['order']
    
    return create_template_response(
        "category_settings.html",
        {
            "request": request,
            "current_user": current_user,
            "categories": all_categories
        }
    )


@app.get("/discover/categories/quick-add", response_class=HTMLResponse)
async def quick_add_categories(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Show quick add interface for additional categories"""
    if not current_user:
        return HTMLResponse('<div class="text-center py-4 text-red-600">Please log in to add categories.</div>')
    
    # Get all available categories
    all_categories = get_default_categories()
    
    # Get user's current preferences
    stmt = select(UserCategoryPreferences).where(UserCategoryPreferences.user_id == current_user.id)
    user_prefs = session.exec(stmt).all()
    prefs_dict = {pref.category_id: pref for pref in user_prefs}
    
    # Find hidden/available categories that user can enable
    available_categories = []
    for category in all_categories:
        cat_id = category['id']
        user_pref = prefs_dict.get(cat_id)
        
        # If user has preference and it's hidden, or no preference and it's an additional category
        is_hidden = (user_pref and not user_pref.is_visible) or (not user_pref and category['order'] > 6)
        
        if is_hidden:
            available_categories.append(category)
    
    return create_template_response(
        "components/quick_add_categories.html",
        {
            "request": request,
            "current_user": current_user,
            "available_categories": available_categories
        }
    )


@app.post("/discover/categories/quick-enable", response_class=HTMLResponse)
async def quick_enable_category(
    request: Request,
    current_user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Quick enable a category and refresh the categories list"""
    if not current_user:
        return HTMLResponse('<div class="text-center py-4 text-red-600">Please log in to enable categories.</div>')
    
    # Get form data
    form = await request.form()
    category_id = form.get("category_id")
    
    if not category_id:
        return HTMLResponse('<div class="text-center py-4 text-red-600">Invalid category.</div>')
    
    # Find the highest current order
    stmt = select(UserCategoryPreferences).where(UserCategoryPreferences.user_id == current_user.id)
    user_prefs = session.exec(stmt).all()
    max_order = max([pref.display_order for pref in user_prefs] + [6])  # Default categories go up to 6
    
    # Check if preference exists
    stmt = select(UserCategoryPreferences).where(
        UserCategoryPreferences.user_id == current_user.id,
        UserCategoryPreferences.category_id == category_id
    )
    existing_pref = session.exec(stmt).first()
    
    if existing_pref:
        # Enable existing preference
        existing_pref.is_visible = True
        existing_pref.display_order = max_order + 1
        existing_pref.updated_at = datetime.utcnow()
    else:
        # Create new preference
        new_pref = UserCategoryPreferences(
            user_id=current_user.id,
            category_id=category_id,
            is_visible=True,
            display_order=max_order + 1
        )
        session.add(new_pref)
    
    session.commit()
    
    # Return updated categories list
    categories = get_user_categories(current_user.id, session)
    
    return create_template_response(
        "components/categories_list.html",
        {
            "request": request,
            "current_user": current_user,
            "categories": categories
        }
    )


@app.get("/discover/categories/customize-mode", response_class=HTMLResponse)
async def categories_customize_mode(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Show customize mode interface for categories"""
    if not current_user:
        return HTMLResponse('<div class="text-center py-8 text-red-600">Please log in to customize categories.</div>')
    
    # Get all available categories
    all_categories = get_default_categories()
    
    # Get user's current preferences
    stmt = select(UserCategoryPreferences).where(UserCategoryPreferences.user_id == current_user.id)
    user_prefs = session.exec(stmt).all()
    prefs_dict = {pref.category_id: pref for pref in user_prefs}
    
    # Separate visible and hidden categories
    visible_categories = []
    hidden_categories = []
    
    for category in all_categories:
        cat_id = category['id']
        user_pref = prefs_dict.get(cat_id)
        
        if user_pref:
            category['user_visible'] = user_pref.is_visible
            category['user_order'] = user_pref.display_order
        else:
            # Default visibility (first 6 categories visible, rest hidden)
            category['user_visible'] = category['order'] <= 6
            category['user_order'] = category['order']
        
        if category['user_visible']:
            visible_categories.append(category)
        else:
            hidden_categories.append(category)
    
    # Sort visible categories by user order
    visible_categories.sort(key=lambda x: x['user_order'])
    
    return create_template_response(
        "components/categories_customize_mode.html",
        {
            "request": request,
            "current_user": current_user,
            "visible_categories": visible_categories,
            "hidden_categories": hidden_categories
        }
    )


@app.post("/discover/categories/save-customizations", response_class=HTMLResponse)
async def save_category_customizations(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Save category customizations and return normal view"""
    if not current_user:
        return HTMLResponse('<div class="text-center py-8 text-red-600">Please log in to save customizations.</div>')
    
    # Get form data
    form = await request.form()
    
    print(f"🔍 Save customizations called for user {current_user.id}")
    print(f"📝 Form data received: {dict(form)}")
    
    # Parse the category preferences from form data
    category_updates = {}
    
    for key, value in form.items():
        if key.endswith('_visible'):
            cat_id = key.replace('_visible', '')
            if cat_id not in category_updates:
                category_updates[cat_id] = {'visible': False, 'order': 0}
            category_updates[cat_id]['visible'] = value == 'on'
        elif key.endswith('_order'):
            cat_id = key.replace('_order', '')
            if cat_id not in category_updates:
                category_updates[cat_id] = {'visible': False, 'order': 0}
            try:
                category_updates[cat_id]['order'] = int(value)
            except (ValueError, TypeError):
                category_updates[cat_id]['order'] = 0
    
    print(f"📊 Parsed category updates: {category_updates}")
    
    # Update database with new preferences
    for cat_id, prefs in category_updates.items():
        # Check if preference exists
        stmt = select(UserCategoryPreferences).where(
            UserCategoryPreferences.user_id == current_user.id,
            UserCategoryPreferences.category_id == cat_id
        )
        existing_pref = session.exec(stmt).first()
        
        if existing_pref:
            # Update existing preference
            print(f"📝 Updating existing preference for {cat_id}: visible={prefs['visible']}, order={prefs['order']}")
            existing_pref.is_visible = prefs['visible']
            existing_pref.display_order = prefs['order']
            existing_pref.updated_at = datetime.utcnow()
        else:
            # Create new preference
            print(f"🆕 Creating new preference for {cat_id}: visible={prefs['visible']}, order={prefs['order']}")
            new_pref = UserCategoryPreferences(
                user_id=current_user.id,
                category_id=cat_id,
                is_visible=prefs['visible'],
                display_order=prefs['order']
            )
            session.add(new_pref)
    
    session.commit()
    print("✅ Database changes committed")
    
    # Return normal categories view
    categories = get_user_categories(current_user.id, session)
    print(f"🎯 Returning {len(categories)} categories after save")
    
    return create_template_response(
        "components/categories_list.html",
        {
            "request": request,
            "current_user": current_user,
            "categories": categories
        }
    )


@app.post("/discover/categories/add-single", response_class=HTMLResponse)
async def add_single_category(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Add a single category without reloading existing ones"""
    if not current_user:
        return HTMLResponse('<div class="text-center py-4 text-red-600">Please log in to add categories.</div>')
    
    # Get form data
    form = await request.form()
    category_id = form.get("category_id")
    
    if not category_id:
        return HTMLResponse('<div class="text-center py-4 text-red-600">Invalid category.</div>')
    
    # Find the category definition
    all_categories = get_default_categories()
    category_def = next((cat for cat in all_categories if cat['id'] == category_id), None)
    
    if not category_def:
        return HTMLResponse('<div class="text-center py-4 text-red-600">Category not found.</div>')
    
    # Find the highest current order
    stmt = select(UserCategoryPreferences).where(UserCategoryPreferences.user_id == current_user.id)
    user_prefs = session.exec(stmt).all()
    max_order = max([pref.display_order for pref in user_prefs] + [6])  # Default categories go up to 6
    
    # Check if preference exists
    stmt = select(UserCategoryPreferences).where(
        UserCategoryPreferences.user_id == current_user.id,
        UserCategoryPreferences.category_id == category_id
    )
    existing_pref = session.exec(stmt).first()
    
    if existing_pref:
        # Enable existing preference
        existing_pref.is_visible = True
        existing_pref.display_order = max_order + 1
        existing_pref.updated_at = datetime.utcnow()
    else:
        # Create new preference
        new_pref = UserCategoryPreferences(
            user_id=current_user.id,
            category_id=category_id,
            is_visible=True,
            display_order=max_order + 1
        )
        session.add(new_pref)
    
    session.commit()
    
    # Return just the new category HTML (not full list)
    category_def['order'] = max_order + 1
    
    # Check if we're in customize mode by looking at the referer or HX-Target header
    hx_target = request.headers.get('HX-Target', '')
    if hx_target == 'visible-categories':
        # We're in customize mode, return a customize item
        return HTMLResponse(f'''
        <div class="customize-category-item bg-white border-2 border-gray-200 rounded-lg p-4 hover:border-gray-300 transition-colors" 
             data-category-id="{category_def['id']}" 
             draggable="true">
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-3">
                    <div class="drag-handle cursor-move text-gray-400 hover:text-gray-600">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8h16M4 16h16"></path>
                        </svg>
                    </div>
                    <div class="w-4 h-4 bg-{category_def['color']}-500 rounded-full"></div>
                    <div>
                        <h4 class="font-medium text-gray-900">{category_def['title']}</h4>
                        <p class="text-sm text-gray-500">Recently added</p>
                    </div>
                </div>
                <div class="flex items-center space-x-3">
                    <button type="button" 
                            onclick="hideCategoryInCustomizeMode('{category_def['id']}', this)"
                            class="text-red-600 hover:text-red-800 p-2 rounded hover:bg-red-50 transition-colors flex items-center space-x-1">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                        </svg>
                        <span class="text-sm">Remove</span>
                    </button>
                </div>
            </div>
        </div>
        <script>
        // Add drag functionality to the newly added item
        const newItem = document.querySelector('[data-category-id="{category_def['id']}"]');
        if (newItem && typeof addDragFunctionality === 'function') {{
            addDragFunctionality(newItem);
        }}
        </script>
        ''')
    else:
        # Normal mode, return the regular category template
        return create_template_response(
            "components/single_category.html",
            {
                "request": request,
                "current_user": current_user,
                "category": category_def
            }
        )


@app.get("/discover/category/expanded", response_class=HTMLResponse)
async def discover_category_expanded(
    request: Request,
    type: str = "movie",
    sort: str = "trending",
    content_sources: list[str] = Query(default=[]),
    genres: list[str] = Query(default=[]),
    rating_source: str = "",
    rating_min: str = "",
    page: int = 1,
    limit: int = 40,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Get expanded category view with infinite scroll"""
    if not current_user:
        return HTMLResponse('<div class="text-center py-8 text-red-600">Please log in to view content.</div>')
    
    # Debug: Print the parameters being received
    print(f"🔍 CATEGORY EXPANDED DEBUG: type='{type}', sort='{sort}', page={page}")
    
    # For expanded content, use grid view to avoid infinite recursion
    return await discover_category(
        request, type, sort, limit, 0, page, "grid", current_user, session
    )

@app.get("/discover/filters", response_class=HTMLResponse)
async def discover_filters(
    request: Request,
    media_type: str = "mixed",
    content_sources: list[str] = Query(default=[]),
    genres: list[str] = Query(default=[]),
    rating_source: str = "",
    rating_min: str = "",
    # Parameters for database categories
    db_category_type: str = Query(default=""),
    db_category_sort: str = Query(default=""),
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Get filter form with current context"""
    return create_template_response(
        "components/discover_filters.html",
        {
            "request": request,
            "current_user": current_user,
            "current_media_type": media_type,
            "current_content_sources": content_sources,
            "current_genres": genres,
            "current_rating_source": rating_source,
            "current_rating_min": rating_min,
            "current_db_category_type": db_category_type,
            "current_db_category_sort": db_category_sort
        }
    )


@app.get("/discover/expand-category", response_class=HTMLResponse)
async def discover_expand_category(
    request: Request,
    type: str = "movie",
    sort: str = "trending",
    title: str = "",
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """HTMX endpoint to expand a category view"""
    if not current_user:
        return HTMLResponse('<div class="text-center py-8 text-red-600">Please log in to view content.</div>')
    
    # Debug: Print the parameters being received
    print(f"🔍 EXPAND CATEGORY DEBUG: type='{type}', sort='{sort}', title='{title}'")
    
    # Return the expanded category view that replaces main-content-area
    return create_template_response(
        "components/expanded_category_view.html",
        {
            "request": request,
            "current_user": current_user,
            "category_title": title,
            "category_type": type,
            "category_sort": sort,
            "base_url": request.app.state.base_url if hasattr(request.app.state, 'base_url') else ""
        }
    )


@app.get("/discover/categories-view", response_class=HTMLResponse)
async def discover_categories_view(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """HTMX endpoint to return to categories view"""
    if not current_user:
        return HTMLResponse('<div class="text-center py-8 text-red-600">Please log in to view content.</div>')
    
    # Return the default categories view that replaces main-content-area
    return create_template_response(
        "components/categories_main_view.html",
        {
            "request": request,
            "current_user": current_user,
            "base_url": request.app.state.base_url if hasattr(request.app.state, 'base_url') else ""
        }
    )


@app.get("/discover/category/more", response_class=HTMLResponse)
async def discover_category_more(
    request: Request,
    type: str = "movie",
    sort: str = "trending",
    content_sources: list[str] = Query(default=[]),
    genres: list[str] = Query(default=[]),
    rating_source: str = "",
    rating_min: str = "",
    page: int = 1,
    limit: int = 40,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Get more items for infinite scroll - returns only the movie cards"""
    if not current_user:
        return HTMLResponse('<div class="text-center py-8 text-red-600">Please log in to view content.</div>')
    
    # Just call the existing discover_category with view="more" to get the cards
    return await discover_category(
        request, type, sort, limit, 0, page, "more", current_user, session
    )


@app.get("/search")
async def search_page(
    request: Request,
    q: str = "",
    page: int = 1,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    if not current_user:
        error_html = '<div class="text-center py-8 text-red-600">Please log in to search content.</div>'
        # Content negotiation - check if this is an HTMX request
        if request.headers.get("HX-Request"):
            from fastapi.responses import HTMLResponse
            return HTMLResponse(error_html)
        else:
            return {"error": "Authentication required", "message": "Please log in to search content"}
    
    if not q:
        empty_context = {"request": request, "results": [], "query": q, "current_user": current_user}
        # Content negotiation - check if this is an HTMX request
        if request.headers.get("HX-Request"):
            return create_template_response("search_results.html", empty_context)
        else:
            return {"results": [], "query": q, "pagination": {"page": 1, "total_pages": 0, "total_results": 0}}
    
    from .services.tmdb_service import TMDBService
    from .services.plex_service import PlexService
    from .services.settings_service import SettingsService
    
    # TMDB now works out of the box with default API key
    
    tmdb_service = TMDBService(session)
    plex_service = PlexService(session)
    
    try:
        # Search TMDB
        search_results = tmdb_service.search_multi(q, page)
        
        # Fast status check using database lookup for movies and TV shows with fallback
        try:
            movie_ids = [item['id'] for item in search_results.get('results', []) if item.get('media_type') == 'movie']
            tv_ids = [item['id'] for item in search_results.get('results', []) if item.get('media_type') == 'tv']
            
            sync_service = PlexSyncService(session)
            movie_status_map = sync_service.check_items_status(movie_ids, 'movie') if movie_ids else {}
            tv_status_map = sync_service.check_items_status(tv_ids, 'tv') if tv_ids else {}
            
            # Add status information to each item
            for item in search_results.get('results', []):
                if item.get('media_type') == 'movie':
                    status = movie_status_map.get(item['id'], 'available')
                    item['status'] = status
                    item['in_plex'] = status == 'in_plex'
                elif item.get('media_type') == 'tv':
                    status = tv_status_map.get(item['id'], 'available')
                    item['status'] = status
                    item['in_plex'] = status == 'in_plex'
                else:
                    item['in_plex'] = False
                    item['status'] = 'not_media'
        except Exception as sync_error:
            print(f"Warning: Fast status check failed, falling back to old method: {sync_error}")
            # Fallback to the old method for now
            for item in search_results.get('results', []):
                if item.get('media_type') in ['movie', 'tv']:
                    item['in_plex'] = plex_service.check_media_in_library(item['id'], item['media_type'])
                    item['status'] = 'in_plex' if item['in_plex'] else 'available'
                else:
                    item['in_plex'] = False
                    item['status'] = 'not_media'
    except ValueError as e:
        # Handle TMDB API errors gracefully
        error_context = {
            "request": request,
            "results": [],
            "query": q,
            "tmdb_error": str(e),
            "current_user": current_user
        }
        # Content negotiation for errors
        if request.headers.get("HX-Request"):
            return create_template_response("search_results.html", error_context)
        else:
            return {"error": "TMDB API error", "message": str(e), "results": [], "query": q}
    
    pagination = {
        'page': page,
        'total_pages': search_results.get('total_pages', 1),
        'total_results': search_results.get('total_results', 0)
    }
    
    # Filter out non-media results and add full poster URLs
    filtered_results = []
    for item in search_results.get('results', []):
        if item.get('media_type') in ['movie', 'tv']:
            # Add full poster URL
            if item.get('poster_path'):
                item['poster_url'] = f"{tmdb_service.image_base_url}{item['poster_path']}"
            filtered_results.append(item)
    
    # Content negotiation based on client type
    if request.headers.get("HX-Request"):
        # HTMX web client - return HTML fragment
        return create_template_response(
            "search_results.html",
            {
                "request": request,
                "results": filtered_results,
                "query": q,
                "pagination": pagination,
                "current_user": current_user
            }
        )
    else:
        # API client (mobile, etc.) - return JSON
        return {
            "success": True,
            "results": filtered_results,
            "query": q,
            "pagination": pagination
        }


@app.get("/media/{media_type}/{media_id}", response_class=HTMLResponse)
async def media_detail(
    request: Request,
    media_type: str,
    media_id: int,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Show detailed media information page"""
    if not current_user:
        return RedirectResponse(url=build_app_url("/login"), status_code=status.HTTP_302_FOUND)
    
    if media_type not in ['movie', 'tv']:
        return HTMLResponse('<div class="text-center py-8 text-red-600">Invalid media type.</div>')
    
    from .services.tmdb_service import TMDBService
    from .services.plex_sync_service import PlexSyncService
    
    tmdb_service = TMDBService(session)
    
    try:
        # Get basic media information from TMDB
        if media_type == 'movie':
            media = tmdb_service.get_movie_details(media_id)
        else:  # tv
            media = tmdb_service.get_tv_details(media_id)
        
        if not media:
            context = {
                "request": request,
                "current_user": current_user,
                "error_message": "Media not found."
            }
            return create_template_response("error.html", context)
        
        # Check if media is available in Plex using fast database lookup (same as discovery page)
        sync_service = PlexSyncService(session)
        status_map = sync_service.check_items_status([media_id], media_type)
        plex_status = status_map.get(media_id, 'available')
        is_in_plex = plex_status == 'in_plex'
        
        # Check for existing requests for this media
        from .models.media_request import MediaRequest, RequestStatus
        existing_request_statement = select(MediaRequest).where(
            MediaRequest.tmdb_id == media_id,
            MediaRequest.media_type == media_type,
            MediaRequest.status.in_([RequestStatus.PENDING, RequestStatus.APPROVED])
        )
        existing_requests = session.exec(existing_request_statement).all()
        
        # Determine request status and availability
        request_status = None
        has_complete_request = False
        has_partial_requests = False
        user_partial_requests = []
        
        if existing_requests:
            # Check if there's a complete series request (no season_number specified)
            complete_request = next((req for req in existing_requests if not req.is_season_request), None)
            if complete_request:
                has_complete_request = True
                request_status = complete_request.status.value
            else:
                # Only partial requests exist
                has_partial_requests = True
                # Get user's partial requests to show appropriate UI
                user_partial_requests = [req for req in existing_requests if req.user_id == current_user.id] if current_user else []
                # Use the status of the most recent partial request
                if user_partial_requests:
                    request_status = user_partial_requests[-1].status.value
        
        # For template context, use the first existing request or None
        existing_request = existing_requests[0] if existing_requests else None
        
        # Add poster URL and status information
        if media.get('poster_path'):
            media['poster_url'] = f"{tmdb_service.image_base_url}{media['poster_path']}"
        
        # Add status information to the main media object
        media['in_plex'] = is_in_plex
        media['status'] = plex_status
        
        # Set request_status based on existing request or plex_status
        if existing_request:
            if existing_request.status == RequestStatus.PENDING:
                media['request_status'] = 'requested_pending'
            elif existing_request.status == RequestStatus.APPROVED:
                media['request_status'] = 'requested_approved'
            elif existing_request.status == RequestStatus.AVAILABLE:
                media['request_status'] = 'in_plex'
            elif existing_request.status == RequestStatus.REJECTED:
                media['request_status'] = 'requested_rejected'
        elif plex_status.startswith('requested_'):
            # If PlexSyncService returned a request status, use it
            media['request_status'] = plex_status 
        
        # Get additional data
        if media_type == 'movie':
            similar = tmdb_service.get_movie_similar(media_id)
            recommendations = tmdb_service.get_movie_recommendations(media_id)
            credits = tmdb_service.get_movie_credits(media_id)
        else:  # tv
            similar = tmdb_service.get_tv_similar(media_id)
            recommendations = tmdb_service.get_tv_recommendations(media_id)
            credits = tmdb_service.get_tv_credits(media_id)
        
        # Add Plex availability status to similar and recommended items using fast lookup
        for item_list in [similar.get('results', []) if similar else [], recommendations.get('results', []) if recommendations else []]:
            if item_list:
                # Batch check Plex status for all items
                tmdb_ids = [item['id'] for item in item_list]
                plex_status_map = sync_service.check_items_status(tmdb_ids, media_type)
                
                # Batch check existing requests for all items to avoid N+1 queries
                item_request_statement = select(MediaRequest).where(
                    MediaRequest.tmdb_id.in_(tmdb_ids),
                    MediaRequest.media_type == media_type,
                    MediaRequest.status.in_([RequestStatus.PENDING, RequestStatus.APPROVED])
                )
                existing_requests = session.exec(item_request_statement).all()
                
                # Create a lookup map for existing requests
                request_map = {req.tmdb_id: req for req in existing_requests}
                
                for item in item_list:
                    item['media_type'] = media_type  # Ensure media type is set
                    
                    # Get Plex status from batch lookup
                    item_plex_status = plex_status_map.get(item['id'], 'available')
                    item['in_plex'] = item_plex_status == 'in_plex'
                    
                    # Check for existing request from batch lookup
                    item_existing_request = request_map.get(item['id'])
                    
                    # Set status for consistency with other templates
                    if item_plex_status == 'in_plex':
                        item['status'] = 'in_plex'
                    elif item_plex_status == 'partial_plex':
                        item['status'] = 'partial_plex'
                    elif item_existing_request:
                        if item_existing_request.status == RequestStatus.PENDING:
                            item['status'] = 'requested_pending'
                        elif item_existing_request.status == RequestStatus.APPROVED:
                            item['status'] = 'requested_approved'
                    else:
                        item['status'] = 'available'
        
        # Check if user has admin permissions using new unified function
        from .core.permissions import is_user_admin
        user_is_admin = is_user_admin(current_user, session)
        
        context = {
            "request": request,
            "current_user": current_user,
            "user_is_admin": user_is_admin,
            "media": media,
            "media_type": media_type,
            "is_in_plex": is_in_plex,
            "plex_status": plex_status,
            "request_status": request_status,
            "existing_request": existing_request,
            "has_complete_request": has_complete_request,
            "has_partial_requests": has_partial_requests,
            "user_partial_requests": user_partial_requests,
            "similar": similar.get('results', [])[:12] if similar else [],
            "recommendations": recommendations.get('results', [])[:12] if recommendations else [],
            "cast": credits.get('cast', [])[:10] if credits else [],
            "crew": credits.get('crew', []) if credits else []
        }
        
        return create_template_response("media_detail_simple.html", context)
        
    except Exception as e:
        print(f"Error loading media details: {e}")
        context = {
            "request": request,
            "current_user": current_user,
            "error_message": f"Error loading media details: {str(e)}"
        }
        return create_template_response("error.html", context)


@app.get("/debug/media/{media_type}/{media_id}")
async def debug_media_detail(
    media_type: str,
    media_id: int,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Debug endpoint to check media detail data"""
    from .core.permissions import is_user_admin
    if not current_user or not is_user_admin(current_user, session):
        return {"error": "Admin access required"}
    
    from .services.tmdb_service import TMDBService
    tmdb_service = TMDBService(session)
    
    try:
        print(f"🔍 Debug: Starting API call for {media_type} {media_id}")
        if media_type == 'movie':
            media = tmdb_service.get_movie_details(media_id)
        else:
            media = tmdb_service.get_tv_details(media_id)
        
        print(f"🔍 Debug: Got media data, title: {media.get('title') or media.get('name')}")
        
        return {
            "success": True,
            "media_basic": {
                "title": media.get('title') or media.get('name'),
                "vote_average": media.get('vote_average'),
                "imdb_id": media.get('imdb_id'),
                "id": media.get('id'),
                "overview": media.get('overview', '')[:100] + "..." if media.get('overview') else None
            }
        }
    except Exception as e:
        print(f"❌ Debug: Error in API call: {e}")
        return {"error": str(e)}

@app.get("/test/simple/{media_type}/{media_id}", response_class=HTMLResponse)
async def test_simple_media(
    media_type: str,
    media_id: int,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Ultra-simple test endpoint"""
    if not current_user:
        return HTMLResponse('<div>Please log in</div>')
    
    try:
        from .services.tmdb_service import TMDBService
        tmdb_service = TMDBService(session)
        
        print(f"🔍 Test: Getting {media_type} {media_id}")
        if media_type == 'movie':
            media = tmdb_service.get_movie_details(media_id)
        else:
            media = tmdb_service.get_tv_details(media_id)
        
        print(f"🔍 Test: Got media data")
        
        html = f"""
        <html>
        <head><title>Test</title></head>
        <body>
            <h1>{media.get('title') or media.get('name')}</h1>
            <p>ID: {media.get('id')}</p>
            <p>Rating: {media.get('vote_average')}</p>
            <p>Type: {media_type}</p>
        </body>
        </html>
        """
        
        return HTMLResponse(html)
        
    except Exception as e:
        print(f"❌ Test: Error: {e}")
        return HTMLResponse(f'<div>Error: {str(e)}</div>')

@app.get("/person/{person_id}", response_class=HTMLResponse)
async def person_detail(
    request: Request,
    person_id: int,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Show person details with movies/TV shows they've been in"""
    if not current_user:
        return HTMLResponse('<div class="text-center py-8 text-red-600">Please log in to view person details.</div>')
    
    from .services.tmdb_service import TMDBService
    from .services.plex_sync_service import PlexSyncService
    
    tmdb_service = TMDBService(session)
    sync_service = PlexSyncService(session)
    
    try:
        # Get person details
        person = tmdb_service.get_person_details(person_id)
        if not person:
            return HTMLResponse('<div class="text-center py-8 text-red-600">Person not found.</div>')
        
        # Get their movie and TV credits
        movie_credits = tmdb_service.get_person_movie_credits(person_id)
        tv_credits = tmdb_service.get_person_tv_credits(person_id)
        
        # Combine and sort by popularity/date
        all_credits = []
        if movie_credits.get('cast'):
            for movie in movie_credits['cast']:
                movie['media_type'] = 'movie'
                all_credits.append(movie)
        
        if tv_credits.get('cast'):
            for show in tv_credits['cast']:
                show['media_type'] = 'tv'
                all_credits.append(show)
        
        # Sort by popularity and limit to top 20
        all_credits = sorted(all_credits, key=lambda x: x.get('popularity', 0), reverse=True)[:20]
        
        # Check Plex status for all credits
        movie_ids = [item['id'] for item in all_credits if item['media_type'] == 'movie']
        tv_ids = [item['id'] for item in all_credits if item['media_type'] == 'tv']
        
        movie_status = sync_service.check_items_status(movie_ids, 'movie') if movie_ids else {}
        tv_status = sync_service.check_items_status(tv_ids, 'tv') if tv_ids else {}
        
        # Add status to items
        for item in all_credits:
            if item['media_type'] == 'movie':
                status = movie_status.get(item['id'], 'available')
                item['in_plex'] = status == 'in_plex'
            else:
                status = tv_status.get(item['id'], 'available')
                item['in_plex'] = status == 'in_plex'
        
        # Add profile image URL
        if person.get('profile_path'):
            person['profile_url'] = f"https://image.tmdb.org/t/p/w500{person['profile_path']}"
        
        return create_template_response(
            "person_detail.html",
            {
                "request": request,
                "person": person,
                "credits": all_credits,
                "current_user": current_user
            }
        )
        
    except Exception as e:
        print(f"Error loading person details: {e}")
        return HTMLResponse(f'<div class="text-center py-8 text-red-600">Error loading person details: {str(e)}</div>')


@app.get("/debug/show/{tmdb_id}")
async def debug_show_sync(
    tmdb_id: int,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Debug endpoint to check why a specific show isn't syncing"""
    from .core.permissions import is_user_admin
    if not current_user or not is_user_admin(current_user, session):
        return {"error": "Admin access required"}
    
    from .services.plex_sync_service import PlexSyncService
    sync_service = PlexSyncService(session)
    return sync_service.debug_show_sync(tmdb_id)

@app.get("/debug/library")
async def debug_library_guids(
    search: str = Query(None, description="Search term to filter shows"),
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Debug endpoint to show all GUIDs in the TV library"""
    from .core.permissions import is_user_admin
    if not current_user or not is_user_admin(current_user, session):
        return {"error": "Admin access required"}
    
    from .services.plex_sync_service import PlexSyncService
    sync_service = PlexSyncService(session)
    return sync_service.debug_library_guids(search)

@app.get("/debug/match/{title}")
async def debug_title_match(
    title: str,
    year: int = Query(..., description="Year of the show/movie"),
    media_type: str = Query("tv", description="Media type: movie or tv"),
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Debug endpoint to test title/year matching"""
    from .core.permissions import is_user_admin
    if not current_user or not is_user_admin(current_user, session):
        return {"error": "Admin access required"}
    
    from .services.plex_sync_service import PlexSyncService
    sync_service = PlexSyncService(session)
    tmdb_id = await sync_service._match_by_title_year(title, year, media_type)
    
    return {
        "title": title,
        "year": year,
        "media_type": media_type,
        "matched_tmdb_id": tmdb_id,
        "expected_tmdb_id": 1407 if title.lower() == "homeland" else None
    }

@app.get("/debug/completion/{tmdb_id}")
async def debug_tv_completion(
    tmdb_id: int,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Debug endpoint to check TV show completion status"""
    from .core.permissions import is_user_admin
    if not current_user or not is_user_admin(current_user, session):
        return {"error": "Admin access required"}
    
    from .services.plex_sync_service import PlexSyncService
    sync_service = PlexSyncService(session)
    return sync_service.debug_tv_completion(tmdb_id)

@app.get("/debug/user")
async def debug_user_status(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Debug endpoint to check user status"""
    if not current_user:
        return {"error": "Not authenticated"}
    
    # Get all users for debugging
    from sqlmodel import select
    all_users = session.exec(select(User)).all()
    admin_users = session.exec(select(User).where(User.is_admin == True)).all()
    
    return {
        "current_user": {
            "id": current_user.id,
            "username": current_user.username,
            "is_admin": current_user.is_admin,
            "is_active": current_user.is_active
        },
        "total_users": len(all_users),
        "total_admins": len(admin_users),
        "all_users": [
            {
                "id": user.id,
                "username": user.username,
                "is_admin": user.is_admin,
                "is_active": user.is_active
            } for user in all_users
        ]
    }


@app.post("/debug/make-admin")
async def make_current_user_admin(
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Emergency endpoint to make current user admin"""
    if not current_user:
        return {"error": "Not authenticated"}
    
    # Check if any admin exists
    from sqlmodel import select
    admin_users = session.exec(select(User).where(User.is_admin == True)).all()
    
    if len(admin_users) == 0:
        # No admin exists, make current user admin
        current_user.is_admin = True
        current_user.is_active = True
        session.add(current_user)
        session.commit()
        session.refresh(current_user)
        
        return {
            "success": True,
            "message": f"User '{current_user.username}' is now an admin!",
            "user": {
                "id": current_user.id,
                "username": current_user.username,
                "is_admin": current_user.is_admin,
                "is_active": current_user.is_active
            }
        }
    else:
        return {
            "error": "Admin users already exist",
            "existing_admins": [user.username for user in admin_users]
        }