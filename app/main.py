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
from .models import User, UserCategoryPreferences, UserCustomCategory
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
    tmdb_service,
    year_from: str = "",
    year_to: str = "",
    studios: list[str] = None,
    streaming: list[str] = None
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
                    "category": {
                        "type": media_type,
                        "sort": f"{db_category_type}_{db_category_sort}",
                        "title": f"Filtered {db_category_type.title()} {db_category_sort.replace('_', ' ').title()}"
                    },
                    "category_type": media_type,
                    "category_sort": f"{db_category_type}_{db_category_sort}_filtered",
                    "category_title": f"Filtered {db_category_type.title()} {db_category_sort.replace('_', ' ').title()}",
                    "page": page,
                    "current_page": page,
                    "total_pages": total_pages,
                    "total_results": total_results,
                    "has_more": total_pages > page,
                    # Pass ALL current filter values for infinite scroll (database categories need these too)
                    "current_rating_min": rating_min,
                    "current_rating_source": rating_source,
                    "current_media_type": media_type,
                    "current_content_sources": [],
                    "current_genres": genres,
                    "current_year_from": year_from,  # Pass actual filter values for infinite scroll
                    "current_year_to": year_to,
                    "current_studios": studios or [],  # Pass actual filter values for infinite scroll
                    "current_streaming": streaming or [],  # Pass actual filter values for infinite scroll
                    # Database category specific parameters for infinite scroll
                    "current_db_category_type": db_category_type,
                    "current_db_category_sort": db_category_sort
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
    year_from: str = "",
    year_to: str = "",
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
                current_user, session, tmdb_service,
                year_from, year_to, studios, streaming
            )
        # Convert genres list to comma-separated string for TMDB
        genre_filter = ",".join(genres) if genres else None
        
        # Convert rating to TMDB format (only TMDB ratings are supported by TMDB API)
        rating_filter = None
        if rating_min:
            if rating_source == "tmdb" or not rating_source:  # Default to TMDB if no source specified
                rating_filter = float(rating_min)
            elif rating_source == "imdb":
                # IMDb uses 0-10 scale like TMDB, so we can use the same value
                # Note: This filters by TMDB rating, not actual IMDb rating
                rating_filter = float(rating_min)
            elif rating_source == "rotten_tomatoes":
                # Convert RT 0-100 scale to TMDB 0-10 scale as approximation
                # Note: This filters by TMDB rating, not actual RT rating
                rating_filter = float(rating_min) / 10.0
        
        # Process year range filters
        year_from_filter = None
        year_to_filter = None
        if year_from and year_from.isdigit():
            year_from_filter = int(year_from)
        if year_to and year_to.isdigit():
            year_to_filter = int(year_to)
        
        # Convert streaming providers to comma-separated string for TMDB
        streaming_filter = ",".join(streaming) if streaming else None
        
        # Handle studio filtering - need different logic for movies vs TV shows
        # For movies: use with_companies
        # For TV shows: use with_networks for actual networks, with_companies for production companies
        movie_studios_filter = ",".join(studios) if studios else None
        tv_networks_filter = None
        tv_companies_filter = None
        
        if studios:
            # Separate networks from production companies for TV filtering
            networks = []  # Actual TV networks
            companies = []  # Production companies that also work for TV
            
            for studio_id in studios:
                # Known TV networks (use with_networks for TV)
                if studio_id in ["213", "49", "2739", "1024", "384", "16", "67", "174", "2"]:  # Netflix, HBO, Disney+, Amazon, HBO Max, CBS, FOX, Warner Bros TV, Disney
                    networks.append(studio_id)
                    companies.append(studio_id)  # Also check as company for some content
                # Known production companies (use with_companies for both movies and TV)
                elif studio_id in ["420", "2", "174", "33", "5", "4"]:  # Marvel, Disney, Warner Bros, Universal, Columbia, Paramount
                    companies.append(studio_id)
                    # For Marvel specifically, also check common Marvel TV networks
                    if studio_id == "420":  # Marvel Studios
                        # Add Disney+ and ABC as they often distribute Marvel TV content
                        networks.extend(["2739", "2"])  # Disney+, Disney
                else:
                    # Default: treat as both
                    networks.append(studio_id)
                    companies.append(studio_id)
            
            tv_networks_filter = ",".join(set(networks)) if networks else None
            tv_companies_filter = ",".join(set(companies)) if companies else None
        
        print(f"🔍 STUDIO FILTER DEBUG: movie_studios={movie_studios_filter}, tv_networks={tv_networks_filter}, tv_companies={tv_companies_filter}")
        
        # Check if we should use pure TMDB discover endpoint instead of content sources
        # Use discover endpoint when no content sources OR when filters are applied (filters take priority)
        has_any_filters = bool(
            genre_filter or rating_filter or streaming_filter or 
            year_from_filter or year_to_filter or 
            movie_studios_filter or tv_networks_filter or tv_companies_filter
        )
        
        use_discover_endpoint = (
            not content_sources or  # No sources selected
            len(content_sources) == 0 or  # Empty sources list
            has_any_filters  # Filters applied - prioritize discover endpoint for accuracy
        )
        
        print(f"🔍 DISCOVER DEBUG - Content sources received: {content_sources}")
        print(f"🔍 DISCOVER DEBUG - Use discover endpoint: {use_discover_endpoint}")
        print(f"🔍 DISCOVER DEBUG - Media type: {media_type}")
        print(f"🔍 DISCOVER DEBUG - Genres: {genres}")
        print(f"🔍 DISCOVER DEBUG - Rating filter: {rating_filter}")
        print(f"🔍 DISCOVER DEBUG - Year range: {year_from_filter} to {year_to_filter}")
        print(f"🔍 DISCOVER DEBUG - Studios filter: movie={movie_studios_filter}, tv_networks={tv_networks_filter}, tv_companies={tv_companies_filter}")
        
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
                            with_companies=movie_studios_filter,
                            primary_release_date_gte=year_from_filter,
                            primary_release_date_lte=year_to_filter,
                        )
                    else:  # tv
                        # For TV shows, try both networks and companies to catch all content
                        # TMDB discover/tv supports both with_networks and with_companies
                        discover_results = tmdb_service.discover_tv(
                            page=page,
                            sort_by="popularity.desc",  # Sort by popularity but search all content
                            with_genres=genre_filter,
                            vote_average_gte=rating_filter,
                            with_watch_providers=streaming_filter,
                            with_networks=tv_networks_filter,
                            with_companies=tv_companies_filter,
                            first_air_date_gte=year_from_filter,
                            first_air_date_lte=year_to_filter,
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
            # Use the unified category system for consistency with /discover/category
            def fetch_from_source(source, target_media_type):
                try:
                    # Use unified category system for all sources
                    # This ensures consistency between horizontal scroll and expanded views
                    # CRITICAL FIX: Added debug logging and proper date parameter mapping
                    print(f"🔍 INFINITE SCROLL DEBUG - Calling get_category_content for {target_media_type}, source={source}")
                    print(f"🔍 INFINITE SCROLL DEBUG - Year filters: {year_from_filter} to {year_to_filter}")
                    print(f"🔍 INFINITE SCROLL DEBUG - Will map to {'primary_release_date' if target_media_type == 'movie' else 'first_air_date'}")
                    
                    return tmdb_service.get_category_content(
                        media_type=target_media_type,
                        category=source,
                        page=page,
                        with_genres=genre_filter,
                        vote_average_gte=rating_filter,
                        with_companies=tv_companies_filter if target_media_type == "tv" else movie_studios_filter,
                        with_networks=tv_networks_filter if target_media_type == "tv" else None,
                        with_watch_providers=streaming_filter,
                        primary_release_date_gte=year_from_filter if target_media_type == "movie" else None,
                        primary_release_date_lte=year_to_filter if target_media_type == "movie" else None,
                        first_air_date_gte=year_from_filter if target_media_type == "tv" else None,
                        first_air_date_lte=year_to_filter if target_media_type == "tv" else None
                    )
                except ValueError as ve:
                    # Category not found in unified system - fallback for unsupported categories
                    print(f"Category '{source}' not found in unified system for {target_media_type}, falling back to popular: {ve}")
                    try:
                        # CRITICAL FIX: Added proper date parameter mapping for fallback
                        print(f"🔍 INFINITE SCROLL FALLBACK - Using popular for {target_media_type}")
                        print(f"🔍 INFINITE SCROLL FALLBACK - Year filters: {year_from_filter} to {year_to_filter}")
                        
                        return tmdb_service.get_category_content(
                            media_type=target_media_type,
                            category="popular",
                            page=page,
                            with_genres=genre_filter,
                            vote_average_gte=rating_filter,
                            with_companies=tv_companies_filter if target_media_type == "tv" else movie_studios_filter,
                            with_networks=tv_networks_filter if target_media_type == "tv" else None,
                            with_watch_providers=streaming_filter,
                            primary_release_date_gte=year_from_filter if target_media_type == "movie" else None,
                            primary_release_date_lte=year_to_filter if target_media_type == "movie" else None,
                            first_air_date_gte=year_from_filter if target_media_type == "tv" else None,
                            first_air_date_lte=year_to_filter if target_media_type == "tv" else None
                        )
                    except Exception as fallback_error:
                        print(f"Error in fallback to popular: {fallback_error}")
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
        
        # Initialize results dictionary structure for content negotiation
        results = {
            "results": all_results,
            "total_pages": total_pages,
            "total_results": total_results
        }
        
        # Note: Genre and TMDB rating filtering is now handled server-side via discover endpoints
        # Only apply client-side filtering for cases where server-side filtering isn't available
        
        # Rating filtering is now handled server-side via TMDB discover API for all rating sources
        
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
                        "category": {
                            "type": media_type,
                            "sort": content_sources[0] if content_sources else 'popular',
                            "title": f"Filtered {media_type.title()}s"
                        },
                        "category_type": media_type,
                        "category_sort": content_sources[0] if content_sources else 'popular',
                        "category_title": f"Filtered {media_type.title()}s",
                        "page": page,
                        "current_page": page,
                        "total_pages": results.get('total_pages', 1),
                        "total_results": results.get('total_results', 0),
                        "has_more": results.get('total_pages', 1) > page,
                        # Pass ALL current filter values for infinite scroll
                        "current_rating_min": rating_min,
                        "current_rating_source": rating_source,
                        "current_media_type": media_type,
                        "current_content_sources": content_sources,
                        "current_genres": genres,
                        "current_year_from": year_from,
                        "current_year_to": year_to,
                        "current_studios": studios,
                        "current_streaming": streaming
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
        from fastapi.responses import HTMLResponse
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
            
            context = {
                "request": request, 
                "results": recently_added,
                "current_user": current_user,
                "media_type": "mixed",  # Mixed content type
                "sort_by": sort,
                "has_more": has_more,
                "next_offset": offset + limit,
                "current_offset": offset,
                "base_url": base_url
            }
            
            # Add category object for expanded view
            if view == "expanded":
                context["category"] = {
                    "type": type,
                    "sort": sort,
                    "title": f"{sort.replace('_', ' ').title()} {type.title()}"
                }
                context["current_page"] = page
                # Add empty filter values for infinite scroll compatibility
                context.update({
                    "current_content_sources": [],
                    "current_genres": [],
                    "current_rating_min": "",
                    "current_rating_source": "",
                    "current_year_from": "",
                    "current_year_to": "",
                    "current_studios": [],
                    "current_streaming": []
                })
            
            return create_template_response(template_name, context)
        
        # Handle Recent Requests from database
        elif type == "requests" and sort == "recent":
            try:
                from app.models.media_request import MediaRequest
                from app.models.user import User
                from app.services.settings_service import SettingsService
                from .core.permissions import is_user_admin
                
                # Get user's specific permissions directly from PermissionsService
                from app.services.permissions_service import PermissionsService
                
                permissions_service = PermissionsService(session)
                user_perms_obj = permissions_service.get_user_permissions(current_user.id)
                custom_perms = user_perms_obj.get_custom_permissions() if user_perms_obj else {}
                
                user_is_admin = is_user_admin(current_user, session)
                
                # Check user's specific viewing permissions
                can_view_all_requests = user_is_admin or custom_perms.get('can_view_other_users_requests', False)
                can_view_request_user = user_is_admin or custom_perms.get('can_see_requester_username', False)
                
                # Import the status enum to filter properly
                from app.models.media_request import RequestStatus
                
                # Build optimized query with joins - exclude fulfilled requests
                # Limit: 20 for horizontal scroll, 40 max for expanded view
                max_limit = min(limit, 40)  # Cap at 40 for expanded view, 20 for horizontal
                
                if user_is_admin or can_view_all_requests:
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
                        if user_is_admin or can_view_request_user:
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
                        if user_is_admin or can_view_request_user:
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
                    "show_request_user": can_view_request_user,
                    "can_view_all_requests": can_view_all_requests,
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
                
                context = {
                    "request": request, 
                    "results": all_results,
                    "current_user": current_user,
                    "media_type": "mixed",  # Mixed content type
                    "sort_by": sort,
                    "has_more": has_more,
                    "next_offset": offset + limit,
                    "current_offset": offset,
                    "base_url": base_url
                }
                
                # Add category object for expanded view
                if view == "expanded":
                    context["category"] = {
                        "type": type,
                        "sort": sort,
                        "title": f"{sort.replace('_', ' ').title()} {type.title()}"
                    }
                    context["current_page"] = page
                    # Add empty filter values for infinite scroll compatibility
                    context.update({
                        "current_content_sources": [],
                        "current_genres": [],
                        "current_rating_min": "",
                        "current_rating_source": "",
                        "current_year_from": "",
                        "current_year_to": "",
                        "current_studios": [],
                        "current_streaming": []
                    })
                
                return create_template_response(template_name, context)
                
            except Exception as rec_error:
                print(f"❌ Error generating personalized recommendations: {rec_error}")
                import traceback
                traceback.print_exc()
                return HTMLResponse('<div class="text-center py-8 text-red-600">Error loading personalized recommendations</div>')
        
        # Handle custom user categories
        elif type.startswith("custom_") or (type == "custom" and sort == "user_defined"):
            print(f"🎯 Fetching custom category for user: {current_user.username}")
            
            try:
                # Parse custom category ID - it comes in the type parameter as "custom_123"
                if type.startswith("custom_"):
                    custom_id = type.replace("custom_", "")
                elif type == "custom" and sort == "user_defined":
                    # Fallback: look for custom category ID in other parameters
                    # This shouldn't happen with current implementation but handle it gracefully
                    return HTMLResponse('<div class="text-center py-8 text-red-600">Custom category ID missing</div>')
                else:
                    return HTMLResponse('<div class="text-center py-8 text-red-600">Invalid custom category format</div>')
                
                if not custom_id.isdigit():
                    print(f"❌ Invalid custom category ID: '{custom_id}'")
                    return HTMLResponse('<div class="text-center py-8 text-red-600">Invalid custom category ID</div>')
                
                print(f"🔍 Loading custom category ID: {custom_id}")
                
                # Load custom category from database
                stmt = select(UserCustomCategory).where(
                    UserCustomCategory.id == int(custom_id),
                    UserCustomCategory.user_id == current_user.id,
                    UserCustomCategory.is_active == True
                )
                custom_category = session.exec(stmt).first()
                
                if not custom_category:
                    print(f"❌ Custom category not found for ID: {custom_id}")
                    return HTMLResponse('<div class="text-center py-8 text-red-600">Custom category not found</div>')
                
                print(f"✅ Found custom category: {custom_category.name}")
                
                # Apply custom filters using TMDB discover API
                filters = custom_category.to_category_dict()['filters']
                
                # Determine media type for API calls
                custom_media_type = filters.get('media_type', 'movie')
                if custom_media_type == 'mixed':
                    custom_media_type = 'movie'  # Default to movies for mixed
                
                print(f"🔍 Custom category filters: {filters}")
                
                # Build filter parameters for TMDB discover
                genre_filter = ",".join(filters.get('genres', [])) if filters.get('genres') else None
                rating_filter = float(filters.get('rating_min')) if filters.get('rating_min') else None
                year_from = int(filters.get('year_from')) if filters.get('year_from') else None
                year_to = int(filters.get('year_to')) if filters.get('year_to') else None
                
                # Studios filter (companies for movies, networks for TV)
                studios_filter = ",".join(filters.get('studios', [])) if filters.get('studios') else None
                streaming_filter = ",".join(filters.get('streaming', [])) if filters.get('streaming') else None
                
                # Handle content sources or use discover with filters
                content_sources = filters.get('content_sources', [])
                if content_sources:
                    # Use specific content source endpoints with filters
                    all_results = []
                    for source in content_sources:
                        try:
                            if source == "trending":
                                if custom_media_type == "movie":
                                    source_results = tmdb_service.discover_movies(
                                        page=page, sort_by="popularity.desc",
                                        with_genres=genre_filter, vote_average_gte=rating_filter,
                                        with_companies=studios_filter, with_watch_providers=streaming_filter,
                                        primary_release_date_gte=year_from, primary_release_date_lte=year_to
                                    )
                                else:
                                    source_results = tmdb_service.discover_tv(
                                        page=page, sort_by="popularity.desc",
                                        with_genres=genre_filter, vote_average_gte=rating_filter,
                                        with_networks=studios_filter, with_watch_providers=streaming_filter,
                                        first_air_date_gte=year_from, first_air_date_lte=year_to
                                    )
                            elif source == "popular":
                                if custom_media_type == "movie":
                                    source_results = tmdb_service.discover_movies(
                                        page=page, sort_by="popularity.desc",
                                        with_genres=genre_filter, vote_average_gte=rating_filter,
                                        with_companies=studios_filter, with_watch_providers=streaming_filter,
                                        primary_release_date_gte=year_from, primary_release_date_lte=year_to
                                    )
                                else:
                                    source_results = tmdb_service.discover_tv(
                                        page=page, sort_by="popularity.desc",
                                        with_genres=genre_filter, vote_average_gte=rating_filter,
                                        with_networks=studios_filter, with_watch_providers=streaming_filter,
                                        first_air_date_gte=year_from, first_air_date_lte=year_to
                                    )
                            elif source == "top_rated":
                                if custom_media_type == "movie":
                                    source_results = tmdb_service.discover_movies(
                                        page=page, sort_by="vote_average.desc",
                                        with_genres=genre_filter, vote_average_gte=rating_filter,
                                        with_companies=studios_filter, with_watch_providers=streaming_filter,
                                        primary_release_date_gte=year_from, primary_release_date_lte=year_to
                                    )
                                else:
                                    source_results = tmdb_service.discover_tv(
                                        page=page, sort_by="vote_average.desc",
                                        with_genres=genre_filter, vote_average_gte=rating_filter,
                                        with_networks=studios_filter, with_watch_providers=streaming_filter,
                                        first_air_date_gte=year_from, first_air_date_lte=year_to
                                    )
                            else:
                                continue
                            
                            all_results.extend(source_results.get('results', []))
                        except Exception as e:
                            print(f"Error fetching from {source} for custom category: {e}")
                            continue
                    
                    # Remove duplicates based on ID
                    seen_ids = set()
                    unique_results = []
                    for item in all_results:
                        if item['id'] not in seen_ids:
                            seen_ids.add(item['id'])
                            unique_results.append(item)
                    
                    limited_results = unique_results[:limit]
                    has_more = len(unique_results) > limit
                    
                else:
                    # Use discover API with just filters
                    if custom_media_type == "movie":
                        discover_results = tmdb_service.discover_movies(
                            page=page, sort_by="popularity.desc",
                            with_genres=genre_filter, vote_average_gte=rating_filter,
                            with_companies=studios_filter, with_watch_providers=streaming_filter,
                            primary_release_date_gte=year_from, primary_release_date_lte=year_to
                        )
                    else:
                        discover_results = tmdb_service.discover_tv(
                            page=page, sort_by="popularity.desc",
                            with_genres=genre_filter, vote_average_gte=rating_filter,
                            with_networks=studios_filter, with_watch_providers=streaming_filter,
                            first_air_date_gte=year_from, first_air_date_lte=year_to
                        )
                    
                    limited_results = discover_results.get('results', [])[:limit]
                    has_more = discover_results.get('total_pages', 1) > page
                
                # Add status information
                try:
                    sync_service = PlexSyncService(session)
                    tmdb_ids = [item['id'] for item in limited_results]
                    status_map = sync_service.check_items_status(tmdb_ids, custom_media_type)
                    
                    for item in limited_results:
                        item['media_type'] = custom_media_type
                        status = status_map.get(item['id'], 'available')
                        item['status'] = status
                        item['in_plex'] = status == 'in_plex'
                        item["base_url"] = base_url
                except Exception as status_error:
                    print(f"Warning: Status check failed for custom category: {status_error}")
                    for item in limited_results:
                        item['media_type'] = custom_media_type
                        item['status'] = 'available'
                        item['in_plex'] = False
                        item["base_url"] = base_url
                
                # Return results using same template structure as other categories
                if view == "expanded":
                    template_name = "components/expanded_results.html"
                else:
                    template_name = "category_horizontal.html"
                
                return create_template_response(
                    template_name,
                    {
                        "request": request,
                        "current_user": current_user,
                        "results": limited_results,
                        "category": {
                            "type": type,
                            "sort": sort,
                            "title": custom_category.name if 'custom_category' in locals() else "Custom Category"
                        },
                        "sort_by": sort,
                        "has_more": has_more,
                        "next_offset": offset + limit,
                        "current_offset": offset
                    }
                )
                
            except Exception as custom_error:
                print(f"❌ Error loading custom category: {custom_error}")
                import traceback
                traceback.print_exc()
                return HTMLResponse('<div class="text-center py-8 text-red-600">Error loading custom category</div>')
        
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
                # Use unified category system for consistency with expanded views
                page_results = tmdb_service.get_category_content(
                    media_type=type,
                    category=sort,
                    page=page_num
                )
                
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
        
        context = {
            "request": request, 
            "results": limited_results,
            "current_user": current_user,
            "media_type": type,
            "sort_by": sort,
            "page": page,
            "total_pages": total_pages,
            "has_more": has_more,
            "next_offset": offset + limit,
            "current_offset": offset,
            "base_url": base_url
        }
        
        # Add category object for expanded view
        if view == "expanded":
            context["category"] = {
                "type": type,
                "sort": sort,
                "title": f"{sort.replace('_', ' ').title()} {type.title()}"
            }
            context["current_page"] = page
            # Add empty filter values for infinite scroll compatibility
            context.update({
                "current_content_sources": [],
                "current_genres": [],
                "current_rating_min": "",
                "current_rating_source": "",
                "current_year_from": "",
                "current_year_to": "",
                "current_studios": [],
                "current_streaming": []
            })
        
        return create_template_response(template_name, context)
        
    except Exception as e:
        print(f"Error in discover category: {e}")
        from fastapi.responses import HTMLResponse
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
            'order': 1,
            'limit': 40
        },
        {
            'id': 'recent-requests', 
            'title': '📋 Recent Requests',
            'type': 'requests',
            'sort': 'recent',
            'color': 'purple',
            'order': 2,
            'limit': 20
        },
        {
            'id': 'recommended-for-you',
            'title': '✨ Recommended for You',
            'type': 'recommendations',
            'sort': 'personalized',
            'color': 'pink',
            'order': 3,
            'limit': 20
        },
        {
            'id': 'trending-movies',
            'title': '🔥 Trending Movies', 
            'type': 'movie',
            'sort': 'trending',
            'color': 'red',
            'order': 4,
            'limit': 20
        },
        {
            'id': 'popular-movies',
            'title': '⭐ Popular Movies',
            'type': 'movie', 
            'sort': 'popular',
            'color': 'yellow',
            'order': 5,
            'limit': 20
        },
        {
            'id': 'trending-tv',
            'title': '🔥 Trending TV Shows',
            'type': 'tv',
            'sort': 'trending', 
            'color': 'purple',
            'order': 6,
            'limit': 20
        },
        {
            'id': 'popular-tv',
            'title': '⭐ Popular TV Shows',
            'type': 'tv',
            'sort': 'popular',
            'color': 'indigo', 
            'order': 7,
            'limit': 20
        },
        # Additional categories that users can enable
        {
            'id': 'top-rated-movies',
            'title': '🏆 Top Rated Movies',
            'type': 'movie',
            'sort': 'top_rated',
            'color': 'orange',
            'order': 8,
            'limit': 20
        },
        {
            'id': 'upcoming-movies',
            'title': '🗓️ Upcoming Movies',
            'type': 'movie',
            'sort': 'upcoming',
            'color': 'blue',
            'order': 9,
            'limit': 20
        },
        {
            'id': 'top-rated-tv',
            'title': '🏆 Top Rated TV Shows',
            'type': 'tv',
            'sort': 'top_rated',
            'color': 'emerald',
            'order': 10,
            'limit': 20
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
            # For default categories (first 7), show by default
            # For additional categories (8+), hide by default unless user explicitly enabled
            if category['order'] > 7:
                continue
        
        customized_categories.append(category)
    
    # Get user's custom categories
    custom_stmt = select(UserCustomCategory).where(
        UserCustomCategory.user_id == user_id,
        UserCustomCategory.is_active == True
    ).order_by(UserCustomCategory.display_order)
    custom_categories = session.exec(custom_stmt).all()
    
    # Convert custom categories to category dict format
    for custom_cat in custom_categories:
        customized_categories.append(custom_cat.to_category_dict())
    
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
            # Default visibility (first 7 categories visible, rest hidden)
            category['user_visible'] = category['order'] <= 7
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
        is_hidden = (user_pref and not user_pref.is_visible) or (not user_pref and category['order'] > 7)
        
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
    max_order = max([pref.display_order for pref in user_prefs] + [7])  # Default categories go up to 7
    
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
    
    # Get all built-in categories
    all_categories = get_default_categories()
    
    # Get user's current preferences
    stmt = select(UserCategoryPreferences).where(UserCategoryPreferences.user_id == current_user.id)
    user_prefs = session.exec(stmt).all()
    prefs_dict = {pref.category_id: pref for pref in user_prefs}
    
    # Get user's custom categories
    custom_stmt = select(UserCustomCategory).where(UserCustomCategory.user_id == current_user.id)
    custom_categories = session.exec(custom_stmt).all()
    
    # Separate visible and hidden categories
    visible_categories = []
    hidden_categories = []
    
    # Process built-in categories
    for category in all_categories:
        cat_id = category['id']
        user_pref = prefs_dict.get(cat_id)
        
        if user_pref:
            category['user_visible'] = user_pref.is_visible
            category['user_order'] = user_pref.display_order
        else:
            # Default visibility (first 7 categories visible, rest hidden)
            category['user_visible'] = category['order'] <= 7
            category['user_order'] = category['order']
        
        # Mark as built-in category
        category['is_custom'] = False
        
        if category['user_visible']:
            visible_categories.append(category)
        else:
            hidden_categories.append(category)
    
    # Add custom categories to visible list (they're always visible in customize mode for deletion)
    for custom_cat in custom_categories:
        custom_category = {
            'id': f'custom_{custom_cat.id}',
            'title': custom_cat.name,
            'type': 'custom',
            'sort': 'custom',
            'color': 'purple',  # Default color for custom categories
            'user_visible': True,
            'user_order': 1000 + custom_cat.id,  # Put custom categories at the end
            'is_custom': True,
            'custom_id': custom_cat.id  # Store the actual custom category ID for deletion
        }
        visible_categories.append(custom_category)
    
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


@app.delete("/discover/custom-category/{custom_category_id}")
async def delete_custom_category(
    custom_category_id: int,
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Delete a user's custom category"""
    if not current_user:
        return {"success": False, "message": "Authentication required"}
    
    try:
        # Find the custom category
        stmt = select(UserCustomCategory).where(
            UserCustomCategory.id == custom_category_id,
            UserCustomCategory.user_id == current_user.id
        )
        custom_category = session.exec(stmt).first()
        
        if not custom_category:
            return {"success": False, "message": "Custom category not found"}
        
        # Delete the custom category
        session.delete(custom_category)
        session.commit()
        
        return {"success": True, "message": f"Custom category '{custom_category.name}' deleted successfully"}
        
    except Exception as e:
        session.rollback()
        print(f"Error deleting custom category: {e}")
        return {"success": False, "message": "Failed to delete custom category"}

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
    max_order = max([pref.display_order for pref in user_prefs] + [7])  # Default categories go up to 7
    
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


@app.post("/discover/categories/save-custom", response_class=HTMLResponse)
async def save_custom_category(
    request: Request,
    current_user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Save user's current filters as a custom category"""
    if not current_user:
        return HTMLResponse('<div class="text-center py-4 text-red-600">Please log in to save categories.</div>')
    
    # Get form data
    form = await request.form()
    category_name = form.get("category_name", "").strip()
    color = form.get("color", "purple")
    
    if not category_name:
        return HTMLResponse('<div class="text-center py-4 text-red-600">Category name is required.</div>')
    
    # Validate category name length
    if len(category_name) > 50:
        return HTMLResponse('<div class="text-center py-4 text-red-600">Category name too long (max 50 characters).</div>')
    
    # Check if user already has a category with this name
    stmt = select(UserCustomCategory).where(
        UserCustomCategory.user_id == current_user.id,
        UserCustomCategory.name == category_name,
        UserCustomCategory.is_active == True
    )
    existing_category = session.exec(stmt).first()
    
    if existing_category:
        return HTMLResponse('<div class="text-center py-4 text-red-600">You already have a category with this name.</div>')
    
    # Get the highest display order for user's categories
    stmt = select(UserCustomCategory).where(
        UserCustomCategory.user_id == current_user.id,
        UserCustomCategory.is_active == True
    )
    custom_categories = session.exec(stmt).all()
    max_order = max([cat.display_order for cat in custom_categories] + [999])
    
    # Also check user's default category preferences
    stmt = select(UserCategoryPreferences).where(UserCategoryPreferences.user_id == current_user.id)
    user_prefs = session.exec(stmt).all()
    max_default_order = max([pref.display_order for pref in user_prefs] + [7])
    
    # Set new category order after all existing categories
    new_order = max(max_order, max_default_order) + 1
    
    # Extract filter parameters from form
    media_type = form.get("media_type")
    content_sources = form.getlist("content_sources")
    genres = form.getlist("genres")
    rating_source = form.get("rating_source")
    rating_min = form.get("rating_min")
    year_from = form.get("year_from")
    year_to = form.get("year_to")
    studios = form.getlist("studios")
    streaming = form.getlist("streaming")
    
    # Convert lists to comma-separated strings
    content_sources_str = ",".join(content_sources) if content_sources else None
    genres_str = ",".join(genres) if genres else None
    studios_str = ",".join(studios) if studios else None
    streaming_str = ",".join(streaming) if streaming else None
    
    # Create new custom category
    custom_category = UserCustomCategory(
        user_id=current_user.id,
        name=category_name,
        media_type=media_type if media_type != "mixed" else None,
        content_sources=content_sources_str,
        genres=genres_str,
        rating_source=rating_source,
        rating_min=rating_min,
        year_from=year_from,
        year_to=year_to,
        studios=studios_str,
        streaming=streaming_str,
        color=color,
        display_order=new_order
    )
    
    session.add(custom_category)
    session.commit()
    
    # Return success response
    return HTMLResponse('<div class="text-center py-4 text-green-600">Category saved successfully!</div>')


@app.get("/discover/category/expanded", response_class=HTMLResponse)
async def discover_category_expanded(
    request: Request,
    type: str = "movie",
    sort: str = "trending",
    content_sources: list[str] = Query(default=[]),
    genres: list[str] = Query(default=[]),
    rating_source: str = "",
    rating_min: str = "",
    year_from: str = "",
    year_to: str = "",
    studios: list[str] = Query(default=[]),
    streaming: list[str] = Query(default=[]),
    page: int = 1,
    limit: int = 40,
    # Parameters for database categories
    db_category_type: str = Query(default="", description="Type for database categories (plex, requests, recommendations)"),
    db_category_sort: str = Query(default="", description="Sort for database categories (recently_added, recent, personalized)"),
    # Parameter for custom categories
    custom_category_id: str = Query(default="", description="ID for custom user categories"),
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Get expanded category view with infinite scroll - NOW WITH FILTER SUPPORT"""
    if not current_user:
        return HTMLResponse('<div class="text-center py-8 text-red-600">Please log in to view content.</div>')
    
    # Debug: Print the parameters being received
    print(f"🔍 CATEGORY EXPANDED DEBUG: type='{type}', sort='{sort}', page={page}")
    print(f"🔍 FILTERS RECEIVED: genres={genres}, rating={rating_min}, years={year_from}-{year_to}, studios={studios}, streaming={streaming}")
    
    # Call the main discover endpoint but with applied filters
    from .services.tmdb_service import TMDBService
    from .services.plex_service import PlexService
    from .services.settings_service import SettingsService
    from .services.plex_sync_service import PlexSyncService
        
    base_url = SettingsService.get_base_url(session)
    tmdb_service = TMDBService(session)
    
    try:
        # Handle different category types first
        if db_category_type and db_category_sort:
            # Database categories (recent requests, recommendations, recently added)
            return await filter_database_category(
                request, db_category_type, db_category_sort, type, 
                genres, rating_source, rating_min, page, limit,
                current_user, session, tmdb_service,
                year_from, year_to, studios, streaming
            )
        elif custom_category_id:
            # Custom user categories - load the saved filters and apply them
            from app.models.user_custom_category import UserCustomCategory
            
            stmt = select(UserCustomCategory).where(
                UserCustomCategory.id == int(custom_category_id),
                UserCustomCategory.user_id == current_user.id,
                UserCustomCategory.is_active == True
            )
            custom_category = session.exec(stmt).first()
            
            if not custom_category:
                return HTMLResponse('<div class="text-center py-8 text-red-600">Custom category not found</div>')
            
            # Get the saved filters from the custom category
            filters = custom_category.to_category_dict()['filters']
            
            # Use the saved filters for TMDB discover
            custom_media_type = filters.get('media_type', type)
            if custom_media_type == 'mixed':
                custom_media_type = type  # Use the requested type for mixed categories
            
            # Build discover parameters from saved filters
            results = tmdb_service.discover_movies(
                page=page,
                sort_by=filters.get('sort_by', 'popularity.desc'),
                with_genres=",".join(filters.get('genres', [])) if filters.get('genres') else None,
                vote_average_gte=filters.get('rating_min'),
                primary_release_date_gte=filters.get('year_from'),
                primary_release_date_lte=filters.get('year_to'),
                with_companies=",".join(filters.get('studios', [])) if filters.get('studios') else None,
                with_watch_providers=",".join(filters.get('streaming', [])) if filters.get('streaming') else None
            ) if custom_media_type == 'movie' else tmdb_service.discover_tv(
                page=page,
                sort_by=filters.get('sort_by', 'popularity.desc'),
                with_genres=",".join(filters.get('genres', [])) if filters.get('genres') else None,
                vote_average_gte=filters.get('rating_min'),
                first_air_date_gte=filters.get('year_from'),
                first_air_date_lte=filters.get('year_to'),
                with_companies=",".join(filters.get('studios', [])) if filters.get('studios') else None,
                with_networks=",".join(filters.get('studios', [])) if filters.get('studios') else None,
                with_watch_providers=",".join(filters.get('streaming', [])) if filters.get('streaming') else None
            )
            
            limited_results = results.get('results', [])[:limit]
            has_more = page < results.get('total_pages', 1) and len(limited_results) > 0
            
            # Add Plex status and prepare for template
            sync_service = PlexSyncService(session)
            for item in limited_results:
                item['media_type'] = custom_media_type
                item["base_url"] = base_url
                
            return create_template_response(
                "components/expanded_results.html",
                {
                    "request": request,
                    "current_user": current_user,
                    "results": limited_results,
                    "category": {
                        "type": f"custom_{custom_category_id}",
                        "sort": "user_defined",
                        "title": custom_category.name
                    },
                    "category_title": custom_category.name,
                    "sort_by": "user_defined",
                    "media_type": custom_media_type,
                    "has_more": has_more,
                    "current_page": page,
                    "total_pages": results.get('total_pages', 1),
                    "current_query_params": f"custom_category_id={custom_category_id}&type={custom_media_type}&page={page + 1}",
                }
            )
        
        # Process filter parameters for content source categories
        genre_filter = ",".join(genres) if genres else None
        # Convert rating to TMDB format (only TMDB ratings are supported by TMDB API)
        rating_filter = None
        if rating_min:
            if rating_source == "tmdb" or not rating_source:  # Default to TMDB if no source specified
                rating_filter = float(rating_min)
            elif rating_source == "imdb":
                # IMDb uses 0-10 scale like TMDB, so we can use the same value
                # Note: This filters by TMDB rating, not actual IMDb rating
                rating_filter = float(rating_min)
            elif rating_source == "rotten_tomatoes":
                # Convert RT 0-100 scale to TMDB 0-10 scale as approximation
                # Note: This filters by TMDB rating, not actual RT rating
                rating_filter = float(rating_min) / 10.0
        year_from_filter = int(year_from) if year_from else None
        year_to_filter = int(year_to) if year_to else None
        studios_filter = ",".join(studios) if studios else None
        streaming_filter = ",".join(streaming) if streaming else None
        
        print(f"🔍 PROCESSED FILTERS: genre_filter={genre_filter}, rating_filter={rating_filter}, year_from={year_from_filter}, year_to={year_to_filter}")
        
        # For expanded view, we need to handle both traditional categories and filtered content
        if content_sources and len(content_sources) > 0:
            # Traditional category with additional filters using unified system
            print(f"🔍 EXPANDED: Traditional category '{sort}' with additional filters")
            
            # Smart studio filtering for TV shows - separate networks from production companies
            tv_networks_filter = None
            tv_companies_filter = studios_filter
            
            if type == "tv" and studios_filter:
                studio_ids = studios_filter.split(",") if studios_filter else []
                # Networks (TV-specific)
                tv_networks = [id for id in studio_ids if id in ["213", "49", "2739", "1024"]]  # Netflix, HBO, Disney+, Amazon Studios when used as networks
                # Production companies that also work for TV
                tv_companies = [id for id in studio_ids if id in ["420", "2", "174", "33", "5", "4"]]  # Marvel, Disney Pictures, Warner Bros, Universal, Columbia, Paramount
                
                if tv_networks:
                    tv_networks_filter = ",".join(tv_networks)
                if tv_companies:
                    tv_companies_filter = ",".join(tv_companies)
            
            # Use unified category system with filters
            try:
                # CRITICAL FIX: Added debug logging and proper date parameter mapping
                print(f"🔍 EXPANDED UNIFIED DEBUG - Using unified category system for {type}, category={sort}")
                print(f"🔍 EXPANDED UNIFIED DEBUG - Year filters: {year_from_filter} to {year_to_filter}")
                print(f"🔍 EXPANDED UNIFIED DEBUG - Will map to {'primary_release_date' if type == 'movie' else 'first_air_date'}")
                
                # CRITICAL FIX: Handle mixed media type correctly for date parameters
                if type == "mixed":
                    movie_date_gte = year_from_filter
                    movie_date_lte = year_to_filter
                    tv_date_gte = year_from_filter
                    tv_date_lte = year_to_filter
                    companies_filter = studios_filter  # Use studios for both movie and TV companies in mixed
                    networks_filter = studios_filter   # Also try studios as networks for TV in mixed
                elif type == "movie":
                    movie_date_gte = year_from_filter
                    movie_date_lte = year_to_filter
                    tv_date_gte = None
                    tv_date_lte = None
                    companies_filter = studios_filter
                    networks_filter = None
                else:  # type == "tv"
                    movie_date_gte = None
                    movie_date_lte = None
                    tv_date_gte = year_from_filter
                    tv_date_lte = year_to_filter
                    companies_filter = tv_companies_filter
                    networks_filter = tv_networks_filter
                
                results = tmdb_service.get_category_content(
                    media_type=type,
                    category=sort,
                    page=page,
                    with_genres=genre_filter,
                    vote_average_gte=rating_filter,
                    with_companies=companies_filter,
                    with_networks=networks_filter,
                    with_watch_providers=streaming_filter,
                    primary_release_date_gte=movie_date_gte,
                    primary_release_date_lte=movie_date_lte,
                    first_air_date_gte=tv_date_gte,
                    first_air_date_lte=tv_date_lte
                )
            except ValueError as e:
                print(f"🔍 EXPANDED: Category '{sort}' not found in unified system, falling back to popular")
                # Fallback for unknown categories
                # CRITICAL FIX: Added debug logging for fallback to popular
                print(f"🔍 EXPANDED FALLBACK DEBUG - Falling back to popular for {type}")
                print(f"🔍 EXPANDED FALLBACK DEBUG - Year filters: {year_from_filter} to {year_to_filter}")
                
                # CRITICAL FIX: Handle mixed media type correctly for date parameters in fallback too
                if type == "mixed":
                    movie_date_gte = year_from_filter
                    movie_date_lte = year_to_filter
                    tv_date_gte = year_from_filter
                    tv_date_lte = year_to_filter
                    companies_filter = studios_filter
                    networks_filter = studios_filter
                elif type == "movie":
                    movie_date_gte = year_from_filter
                    movie_date_lte = year_to_filter
                    tv_date_gte = None
                    tv_date_lte = None
                    companies_filter = studios_filter
                    networks_filter = None
                else:  # type == "tv"
                    movie_date_gte = None
                    movie_date_lte = None
                    tv_date_gte = year_from_filter
                    tv_date_lte = year_to_filter
                    companies_filter = tv_companies_filter
                    networks_filter = tv_networks_filter
                
                results = tmdb_service.get_category_content(
                    media_type=type,
                    category="popular",
                    page=page,
                    with_genres=genre_filter,
                    vote_average_gte=rating_filter,
                    with_companies=companies_filter,
                    with_networks=networks_filter,
                    with_watch_providers=streaming_filter,
                    primary_release_date_gte=movie_date_gte,
                    primary_release_date_lte=movie_date_lte,
                    first_air_date_gte=tv_date_gte,
                    first_air_date_lte=tv_date_lte
                )
            
            limited_results = results.get('results', [])
            has_more = results.get('total_pages', 1) > page
            
        else:
            # Pure filtered content (no specific category)
            print(f"🔍 EXPANDED: Pure filtered content search")
            
            if type == "movie":
                results = tmdb_service.discover_movies(
                    page=page, sort_by="popularity.desc",
                    with_genres=genre_filter, vote_average_gte=rating_filter,
                    with_companies=studios_filter, with_watch_providers=streaming_filter,
                    primary_release_date_gte=year_from_filter, primary_release_date_lte=year_to_filter
                )
            elif type == "tv":
                # Smart studio filtering for TV shows - separate networks from production companies
                tv_networks_filter = None
                tv_companies_filter = None
                
                if studios_filter:
                    studio_ids = studios_filter.split(",") if studios_filter else []
                    # Networks (TV-specific)
                    tv_networks = [id for id in studio_ids if id in ["213", "49", "2739", "1024"]]  # Netflix, HBO, Disney+, Amazon Studios when used as networks
                    # Production companies that also work for TV
                    tv_companies = [id for id in studio_ids if id in ["420", "2", "174", "33", "5", "4"]]  # Marvel, Disney Pictures, Warner Bros, Universal, Columbia, Paramount
                    
                    if tv_networks:
                        tv_networks_filter = ",".join(tv_networks)
                    if tv_companies:
                        tv_companies_filter = ",".join(tv_companies)
                
                results = tmdb_service.discover_tv(
                    page=page, sort_by="popularity.desc",
                    with_genres=genre_filter, vote_average_gte=rating_filter,
                    with_networks=tv_networks_filter, with_companies=tv_companies_filter,
                    with_watch_providers=streaming_filter,
                    first_air_date_gte=year_from_filter, first_air_date_lte=year_to_filter
                )
            else:
                # Mixed type - combine results
                movie_results = tmdb_service.discover_movies(
                    page=page, sort_by="popularity.desc",
                    with_genres=genre_filter, vote_average_gte=rating_filter,
                    with_companies=studios_filter, with_watch_providers=streaming_filter,
                    primary_release_date_gte=year_from_filter, primary_release_date_lte=year_to_filter
                )
                # Smart studio filtering for TV shows in mixed mode
                tv_networks_filter = None
                tv_companies_filter = None
                
                if studios_filter:
                    studio_ids = studios_filter.split(",") if studios_filter else []
                    # Networks (TV-specific)
                    tv_networks = [id for id in studio_ids if id in ["213", "49", "2739", "1024"]]  # Netflix, HBO, Disney+, Amazon Studios when used as networks
                    # Production companies that also work for TV
                    tv_companies = [id for id in studio_ids if id in ["420", "2", "174", "33", "5", "4"]]  # Marvel, Disney Pictures, Warner Bros, Universal, Columbia, Paramount
                    
                    if tv_networks:
                        tv_networks_filter = ",".join(tv_networks)
                    if tv_companies:
                        tv_companies_filter = ",".join(tv_companies)
                
                tv_results = tmdb_service.discover_tv(
                    page=page, sort_by="popularity.desc",
                    with_genres=genre_filter, vote_average_gte=rating_filter,
                    with_networks=tv_networks_filter, with_companies=tv_companies_filter,
                    with_watch_providers=streaming_filter,
                    first_air_date_gte=year_from_filter, first_air_date_lte=year_to_filter
                )
                
                # Combine and sort by popularity
                all_results = []
                for item in movie_results.get('results', []):
                    item['media_type'] = 'movie'
                    all_results.append(item)
                for item in tv_results.get('results', []):
                    item['media_type'] = 'tv'
                    all_results.append(item)
                
                # Sort by vote_average * vote_count for popularity
                all_results.sort(key=lambda x: x.get('vote_average', 0) * x.get('vote_count', 0), reverse=True)
                
                limited_results = all_results[:limit]
                has_more = len(all_results) >= limit or movie_results.get('total_pages', 1) > page or tv_results.get('total_pages', 1) > page
                
                results = {"results": limited_results}
            
            if type != "mixed":
                limited_results = results.get('results', [])
                has_more = results.get('total_pages', 1) > page
        
        # Add status information
        try:
            sync_service = PlexSyncService(session)
            tmdb_ids = [item['id'] for item in limited_results]
            
            if type == "mixed":
                # Handle mixed media types
                movie_ids = [item['id'] for item in limited_results if item.get('media_type') == 'movie']
                tv_ids = [item['id'] for item in limited_results if item.get('media_type') == 'tv']
                
                movie_status = sync_service.check_items_status(movie_ids, 'movie') if movie_ids else {}
                tv_status = sync_service.check_items_status(tv_ids, 'tv') if tv_ids else {}
                
                for item in limited_results:
                    if item.get('media_type') == 'movie':
                        status = movie_status.get(item['id'], 'available')
                    else:
                        status = tv_status.get(item['id'], 'available')
                    item['status'] = status
                    item['in_plex'] = status == 'in_plex'
            else:
                # Single media type
                status_map = sync_service.check_items_status(tmdb_ids, type)
                for item in limited_results:
                    item['media_type'] = type
                    status = status_map.get(item['id'], 'available')
                    item['status'] = status
                    item['in_plex'] = status == 'in_plex'
                    item["base_url"] = base_url
        except Exception as status_error:
            print(f"Warning: Status check failed for expanded view: {status_error}")
            for item in limited_results:
                if not item.get('media_type'):
                    item['media_type'] = type
                item['status'] = 'available'
                item['in_plex'] = False
                item["base_url"] = base_url
        
        # Debug output for infinite scroll
        print(f"🔍 EXPANDED CONTEXT DEBUG - has_more: {has_more}, page: {page}, total_pages: {results.get('total_pages', 'unknown')}, results_count: {len(limited_results)}")
        
        # Return expanded grid template
        return create_template_response(
            "components/expanded_results.html",
            {
                "request": request,
                "current_user": current_user,
                "results": limited_results,
                "category": {
                    "type": type,
                    "sort": sort,
                    "title": f"{sort.replace('_', ' ').title()} {type.title()}"
                },
                "sort_by": sort,
                "has_more": has_more,
                "current_page": page,
                "base_url": base_url,
                # Pass current filter values for infinite scroll
                "current_content_sources": content_sources,
                "current_genres": genres,
                "current_rating_min": rating_min,
                "current_rating_source": rating_source,
                "current_year_from": year_from,
                "current_year_to": year_to,
                "current_studios": studios,
                "current_streaming": streaming
            }
        )
        
    except Exception as expanded_error:
        print(f"❌ Error in expanded category view: {expanded_error}")
        import traceback
        traceback.print_exc()
        return HTMLResponse('<div class="text-center py-8 text-red-600">Error loading expanded content</div>')

@app.get("/discover/genres", response_class=HTMLResponse)
async def discover_genres(
    request: Request,
    media_type: str = "movie",
    current_genres: list[str] = Query(default=[]),
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Get dynamic genre list based on media type"""
    if not current_user:
        return HTMLResponse('<div class="text-red-600 text-xs">Please log in to see genres.</div>')
    
    try:
        from .services.tmdb_service import TMDBService
        tmdb_service = TMDBService(session)
        
        # Get genres for the specific media type
        if media_type == "tv":
            genre_data = tmdb_service.get_genre_list("tv")
        elif media_type == "mixed":
            # For mixed media type, get both movie and TV genres and combine them
            movie_genres = tmdb_service.get_genre_list("movie").get('genres', [])
            tv_genres = tmdb_service.get_genre_list("tv").get('genres', [])
            
            # Combine and deduplicate genres by name
            combined_genres = {}
            for genre in movie_genres:
                combined_genres[genre['name']] = genre
            for genre in tv_genres:
                if genre['name'] not in combined_genres:
                    combined_genres[genre['name']] = genre
                else:
                    # If genre exists in both, prefer the movie ID for consistency with TMDB discover
                    # but note that mixed queries will handle both IDs appropriately
                    pass
            
            genre_data = {'genres': list(combined_genres.values())}
        else:
            # Default to movie genres for "movie"
            genre_data = tmdb_service.get_genre_list("movie")
        
        genres = genre_data.get('genres', [])
        
        # Generate HTML for genre checkboxes
        html_content = ""
        for genre in genres:
            genre_id = str(genre['id'])
            genre_name = genre['name']
            checked = 'checked' if genre_id in current_genres else ''
            
            html_content += f'''
            <label class="flex items-center text-xs cursor-pointer hover:bg-gray-50 p-1 rounded">
                <input type="checkbox" name="genres" value="{genre_id}" class="mr-2 text-orange-600 focus:ring-orange-500 h-3 w-3" {checked}>
                {genre_name}
            </label>
            '''
        
        return HTMLResponse(html_content)
        
    except Exception as e:
        print(f"Error fetching genres: {e}")
        return HTMLResponse('<div class="text-red-600 text-xs">Error loading genres</div>')

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
    year_from: str = "",
    year_to: str = "",
    studios: list[str] = Query(default=[]),
    streaming: list[str] = Query(default=[]),
    page: int = 1,
    limit: int = 40,
    # Parameters for database categories
    db_category_type: str = Query(default="", description="Type for database categories (plex, requests, recommendations)"),
    db_category_sort: str = Query(default="", description="Sort for database categories (recently_added, recent, personalized)"),
    # Parameter for custom categories
    custom_category_id: str = Query(default="", description="ID for custom user categories"),
    current_user: User | None = Depends(get_current_user_optional),
    session: Session = Depends(get_session)
):
    """Get more items for infinite scroll - simplified for debugging"""
    if not current_user:
        return HTMLResponse('<div class="text-center py-8 text-red-600">Please log in to view content.</div>')
    
    try:
        # Import required services
        from .services.tmdb_service import TMDBService
        from .services.plex_service import PlexService
        from .services.settings_service import SettingsService
        from .services.plex_sync_service import PlexSyncService
        from fastapi.templating import Jinja2Templates
        
        base_url = SettingsService.get_base_url(session)
        tmdb_service = TMDBService(session)
        templates = Jinja2Templates(directory="app/templates")
        
        # Handle different category types first (same as expanded endpoint)
        if db_category_type and db_category_sort:
            # Database categories (recent requests, recommendations, recently added)
            return await filter_database_category(
                request, db_category_type, db_category_sort, type, 
                genres, rating_source, rating_min, page, limit,
                current_user, session, tmdb_service,
                year_from, year_to, studios, streaming
            )
        elif custom_category_id:
            # Custom user categories - load the saved filters and apply them
            from app.models.user_custom_category import UserCustomCategory
            
            stmt = select(UserCustomCategory).where(
                UserCustomCategory.id == int(custom_category_id),
                UserCustomCategory.user_id == current_user.id,
                UserCustomCategory.is_active == True
            )
            custom_category = session.exec(stmt).first()
            
            if not custom_category:
                return HTMLResponse('<div class="text-center py-8 text-red-600">Custom category not found</div>')
            
            # Get the saved filters from the custom category
            filters = custom_category.to_category_dict()['filters']
            
            # Use the saved filters for TMDB discover
            custom_media_type = filters.get('media_type', type)
            if custom_media_type == 'mixed':
                custom_media_type = type
            
            # Build discover parameters from saved filters
            results = tmdb_service.discover_movies(
                page=page,
                sort_by=filters.get('sort_by', 'popularity.desc'),
                with_genres=",".join(filters.get('genres', [])) if filters.get('genres') else None,
                vote_average_gte=filters.get('rating_min'),
                primary_release_date_gte=filters.get('year_from'),
                primary_release_date_lte=filters.get('year_to'),
                with_companies=",".join(filters.get('studios', [])) if filters.get('studios') else None,
                with_watch_providers=",".join(filters.get('streaming', [])) if filters.get('streaming') else None
            ) if custom_media_type == 'movie' else tmdb_service.discover_tv(
                page=page,
                sort_by=filters.get('sort_by', 'popularity.desc'),
                with_genres=",".join(filters.get('genres', [])) if filters.get('genres') else None,
                vote_average_gte=filters.get('rating_min'),
                first_air_date_gte=filters.get('year_from'),
                first_air_date_lte=filters.get('year_to'),
                with_companies=",".join(filters.get('studios', [])) if filters.get('studios') else None,
                with_networks=",".join(filters.get('studios', [])) if filters.get('studios') else None,
                with_watch_providers=",".join(filters.get('streaming', [])) if filters.get('streaming') else None
            )
            
            limited_results = results.get('results', [])[:limit]
            has_more = page < results.get('total_pages', 1) and len(limited_results) > 0
            
            # Add Plex status and prepare for template
            sync_service = PlexSyncService(session)
            for item in limited_results:
                item['media_type'] = custom_media_type
                item["base_url"] = base_url
                
            return create_template_response(
                "components/movie_cards_only.html",
                {
                    "request": request,
                    "results": limited_results,
                    "has_more": has_more,
                    "current_page": page,
                    "total_pages": results.get('total_pages', 1),
                    "current_query_params": f"custom_category_id={custom_category_id}&type={custom_media_type}&page={page + 1}",
                    "called_from_expanded": True,
                }
            )
        
        # Process filter parameters for content source categories (same logic as discover_category_expanded)
        genre_filter = ",".join(genres) if genres else None
        rating_filter = None
        if rating_min:
            if rating_source == "tmdb" or not rating_source:
                rating_filter = float(rating_min)
            elif rating_source == "imdb":
                rating_filter = float(rating_min)
            elif rating_source == "rotten_tomatoes":
                rating_filter = float(rating_min) / 10.0
        year_from_filter = int(year_from) if year_from else None
        year_to_filter = int(year_to) if year_to else None
        
        # Handle studio/company filtering
        company_filter = None
        if studios:
            company_filter = ",".join(studios)
            
        # Handle streaming service filtering
        streaming_filter = None
        if streaming:
            streaming_filter = ",".join(streaming)
        
        results = []
        total_pages = 1
        
        # Get results based on category type (SAME LOGIC AS MAIN CATEGORY ENDPOINT)
        if type in ['recently-added', 'recent-requests']:
            # Database categories - get from Plex sync data
            plex_sync_service = PlexSyncService(session)
            if type == 'recently-added':
                results = plex_sync_service.get_recently_added_media(limit=limit, offset=(page-1)*limit)
            elif type == 'recent-requests':
                # Get recent requests from database
                from sqlmodel import select
                from .models.request import Request as MediaRequest
                stmt = select(MediaRequest).order_by(MediaRequest.created_at.desc()).limit(limit).offset((page-1)*limit)
                db_results = session.exec(stmt).all()
                results = [{'id': r.tmdb_id, 'title': r.title, 'media_type': r.media_type} for r in db_results]
            # For database results, estimate has_more based on result count
            total_pages = 1000 if len(results) >= limit else page
        elif type.startswith('custom_'):
            # Custom category logic
            from .models.user_custom_category import UserCustomCategory
            from sqlmodel import select
            
            category_id = int(type.split('_')[1])
            stmt = select(UserCustomCategory).where(
                UserCustomCategory.id == category_id,
                UserCustomCategory.user_id == current_user.id
            )
            custom_category = session.exec(stmt).first()
            
            if custom_category:
                # Use custom category filters
                media_type = custom_category.media_type or "movie"
                filters = custom_category.get_filters()
                
                if media_type == "movie":
                    data = tmdb_service.discover_movies(
                        page=page,
                        with_genres=",".join(filters.get('genres', [])) if filters.get('genres') else None,
                        with_companies=",".join(filters.get('studios', [])) if filters.get('studios') else None,
                        with_watch_providers=",".join(filters.get('streaming', [])) if filters.get('streaming') else None,
                        vote_average_gte=float(filters.get('rating_min', 0)) if filters.get('rating_min') else None
                    )
                else:
                    data = tmdb_service.discover_tv(
                        page=page,
                        with_genres=",".join(filters.get('genres', [])) if filters.get('genres') else None,
                        with_companies=",".join(filters.get('studios', [])) if filters.get('studios') else None,
                        with_watch_providers=",".join(filters.get('streaming', [])) if filters.get('streaming') else None,
                        vote_average_gte=float(filters.get('rating_min', 0)) if filters.get('rating_min') else None
                    )
                
                results = data.get('results', [])
                total_pages = data.get('total_pages', 1)
                
                # Add media_type
                for item in results:
                    item['media_type'] = media_type
        else:
            # TMDB API categories using unified system
            print(f"🔍 EXPANDED: Pure category '{sort}' without additional filters")
            
            try:
                # CRITICAL FIX: Added debug logging for pure category call
                print(f"🔍 PURE CATEGORY DEBUG - Pure category {sort} for {type}")
                print(f"🔍 PURE CATEGORY DEBUG - Year filters: {year_from_filter} to {year_to_filter}")
                
                # CRITICAL FIX: Handle mixed media type correctly for date parameters
                # For mixed media, we need to pass BOTH movie and TV date parameters
                if type == "mixed":
                    movie_date_gte = year_from_filter
                    movie_date_lte = year_to_filter
                    tv_date_gte = year_from_filter
                    tv_date_lte = year_to_filter
                elif type == "movie":
                    movie_date_gte = year_from_filter
                    movie_date_lte = year_to_filter
                    tv_date_gte = None
                    tv_date_lte = None
                else:  # type == "tv"
                    movie_date_gte = None
                    movie_date_lte = None
                    tv_date_gte = year_from_filter
                    tv_date_lte = year_to_filter
                
                data = tmdb_service.get_category_content(
                    media_type=type,
                    category=sort,
                    page=page,
                    with_genres=genre_filter,
                    vote_average_gte=rating_filter,
                    with_companies=company_filter,
                    with_networks=None,  # Networks not used in this path
                    with_watch_providers=streaming_filter,
                    primary_release_date_gte=movie_date_gte,
                    primary_release_date_lte=movie_date_lte,
                    first_air_date_gte=tv_date_gte,
                    first_air_date_lte=tv_date_lte
                )
            except ValueError as e:
                print(f"🔍 EXPANDED: Category '{sort}' not found in unified system, falling back to popular")
                # Fallback for unknown categories
                # CRITICAL FIX: Added debug logging for fallback in pure category
                print(f"🔍 PURE CATEGORY FALLBACK DEBUG - Falling back to popular for {type}")
                print(f"🔍 PURE CATEGORY FALLBACK DEBUG - Year filters: {year_from_filter} to {year_to_filter}")
                
                # CRITICAL FIX: Handle mixed media type correctly for date parameters in fallback too
                if type == "mixed":
                    movie_date_gte = year_from_filter
                    movie_date_lte = year_to_filter
                    tv_date_gte = year_from_filter
                    tv_date_lte = year_to_filter
                elif type == "movie":
                    movie_date_gte = year_from_filter
                    movie_date_lte = year_to_filter
                    tv_date_gte = None
                    tv_date_lte = None
                else:  # type == "tv"
                    movie_date_gte = None
                    movie_date_lte = None
                    tv_date_gte = year_from_filter
                    tv_date_lte = year_to_filter
                
                data = tmdb_service.get_category_content(
                    media_type=type,
                    category="popular",
                    page=page,
                    with_genres=genre_filter,
                    vote_average_gte=rating_filter,
                    with_companies=company_filter,
                    with_networks=None,  # Networks not used in this path
                    with_watch_providers=streaming_filter,
                    primary_release_date_gte=movie_date_gte,
                    primary_release_date_lte=movie_date_lte,
                    first_air_date_gte=tv_date_gte,
                    first_air_date_lte=tv_date_lte
                )
            
            results = data.get('results', [])
            total_pages = data.get('total_pages', 1)
        
        # Add media_type to all results for consistency
        for item in results:
            if 'media_type' not in item:
                item['media_type'] = type
            # Skip Plex checks for performance
            item['in_plex'] = False
        
        # Check if there are more results available using TMDB pagination
        has_more = page < total_pages and len(results) > 0
        
        
        # Prepare context for template  
        context = {
            "request": request,
            "results": results,
            "base_url": base_url,
            "has_more": has_more,
            "current_page": page,
            "called_from_expanded": False,  # Allow infinite scroll trigger in movie_cards_only.html
            # Pass all filter parameters for the next page
            "current_query_params": f"type={type}&sort={sort}" + 
                                   (f"&{'&'.join([f'content_sources={cs}' for cs in content_sources])}" if content_sources else "") +
                                   (f"&{'&'.join([f'genres={g}' for g in genres])}" if genres else "") +
                                   (f"&rating_min={rating_min}&rating_source={rating_source}" if rating_min else "") +
                                   (f"&year_from={year_from}" if year_from else "") +
                                   (f"&year_to={year_to}" if year_to else "") +
                                   (f"&{'&'.join([f'studios={s}' for s in studios])}" if studios else "") +
                                   (f"&{'&'.join([f'streaming={s}' for s in streaming])}" if streaming else "")
        }
        
        return templates.TemplateResponse("components/movie_cards_only.html", context)
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return HTMLResponse(f'<div class="text-center py-8 text-red-600">Error: {str(e)}</div>')


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
            # Check if there's a complete series request (no season_number and no episode_number specified)
            complete_request = next((req for req in existing_requests if not req.is_season_request and not req.is_episode_request), None)
            if complete_request:
                has_complete_request = True
                request_status = complete_request.status.value
            else:
                # Only partial requests exist (season or episode requests)
                has_partial_requests = True
                # Get user's partial requests to show appropriate UI
                user_partial_requests = [req for req in existing_requests if req.user_id == current_user.id] if current_user else []
                # Use the status of the most recent partial request
                if user_partial_requests:
                    request_status = user_partial_requests[-1].status.value
        
        # For template context, use the first existing request or None
        existing_request = existing_requests[0] if existing_requests else None
        
        # Create detailed request status for template
        requested_seasons = set()
        requested_episodes = {}  # {season_number: [episode_numbers]}
        for req in existing_requests:
            if req.is_season_request and req.season_number:
                requested_seasons.add(req.season_number)
            elif req.is_episode_request and req.season_number and req.episode_number:
                if req.season_number not in requested_episodes:
                    requested_episodes[req.season_number] = []
                requested_episodes[req.season_number].append(req.episode_number)
        
        # Add poster and backdrop URLs
        if media.get('poster_path'):
            media['poster_url'] = f"{tmdb_service.image_base_url}{media['poster_path']}"
        if media.get('backdrop_path'):
            media['backdrop_url'] = f"https://image.tmdb.org/t/p/w1920_and_h800_multi_faces{media['backdrop_path']}"
        
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
            
            # Fetch detailed episode information for each season
            if media.get('seasons'):
                for season in media['seasons']:
                    # Only fetch details for seasons with episodes (skip specials if episode count is 0)
                    if season.get('episode_count', 0) > 0:
                        try:
                            season_details = tmdb_service.get_tv_season_details(media_id, season['season_number'])
                            if season_details and season_details.get('episodes'):
                                # Replace the basic episode count with detailed episode data
                                season['episodes'] = season_details['episodes']
                                # Add formatted air dates for easier template use
                                for episode in season['episodes']:
                                    if episode.get('air_date'):
                                        try:
                                            from datetime import datetime
                                            air_date = datetime.strptime(episode['air_date'], '%Y-%m-%d')
                                            episode['formatted_air_date'] = air_date.strftime('%b %d, %Y')
                                        except ValueError:
                                            episode['formatted_air_date'] = episode['air_date']
                                    else:
                                        episode['formatted_air_date'] = 'TBA'
                        except Exception as e:
                            print(f"Could not fetch season {season['season_number']} details: {e}")
                            # Keep basic episode list if detailed fetch fails
                            season['episodes'] = None
            
            # Get episode availability data from Plex
            episode_availability = sync_service.get_tv_episode_availability(media_id)
            media['episode_availability'] = episode_availability
            
            # Add availability info to each season and episode
            if media.get('seasons') and episode_availability.get('seasons'):
                for season in media['seasons']:
                    season_num = season['season_number']
                    plex_season_data = episode_availability['seasons'].get(season_num, {})
                    
                    # Mark if season is available in Plex
                    season['available_in_plex'] = season_num in episode_availability['summary']['available_season_numbers']
                    
                    # Add availability to individual episodes
                    if season.get('episodes') and plex_season_data.get('episodes'):
                        available_episodes = {ep['episode_number']: ep for ep in plex_season_data['episodes']}
                        for episode in season['episodes']:
                            ep_num = episode['episode_number']
                            episode['available_in_plex'] = ep_num in available_episodes
        
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
        
        # Get user permissions for request capabilities
        from .services.permissions_service import PermissionsService
        permissions_service = PermissionsService(session)
        
        # Create user permissions object with boolean attributes for template
        class UserPermissionsTemplate:
            def __init__(self, permissions_service, user_id):
                self.can_request_movies = permissions_service.can_request_media_type(user_id, 'movie') if user_id else False
                self.can_request_tv = permissions_service.can_request_media_type(user_id, 'tv') if user_id else False
                self.can_request_4k = permissions_service.can_request_4k(user_id) if user_id else False
                # Add admin navigation permissions needed by base template
                # Import PermissionFlags to use correct constants
                from .models.role import PermissionFlags
                
                # Add error handling for permission checks to prevent 500 errors for Plex users
                try:
                    self.can_manage_settings = permissions_service.has_permission(user_id, PermissionFlags.ADMIN_MANAGE_SETTINGS) if user_id else False
                    self.can_manage_users = permissions_service.has_permission(user_id, PermissionFlags.ADMIN_MANAGE_USERS) if user_id else False
                    self.can_approve_requests = permissions_service.has_permission(user_id, PermissionFlags.ADMIN_APPROVE_REQUESTS) if user_id else False
                    self.can_library_sync = permissions_service.has_permission(user_id, PermissionFlags.ADMIN_LIBRARY_SYNC) if user_id else False
                except Exception as e:
                    print(f"⚠️ Error checking admin permissions for user {user_id}: {e}")
                    # Default to False for all admin permissions if error occurs
                    self.can_manage_settings = False
                    self.can_manage_users = False
                    self.can_approve_requests = False
                    self.can_library_sync = False
        
        user_permissions = UserPermissionsTemplate(permissions_service, current_user.id) if current_user else None
        
        # Get base URL for templates
        from .services.settings_service import SettingsService
        base_url = SettingsService.get_base_url(session)
        
        context = {
            "request": request,
            "current_user": current_user,
            "user_is_admin": user_is_admin,
            "user_permissions": user_permissions,
            "base_url": base_url,
            "media": media,
            "media_type": media_type,
            "is_in_plex": is_in_plex,
            "plex_status": plex_status,
            "request_status": request_status,
            "existing_request": existing_request,
            "has_complete_request": has_complete_request,
            "has_partial_requests": has_partial_requests,
            "user_partial_requests": user_partial_requests,
            "requested_seasons": requested_seasons,
            "requested_episodes": requested_episodes,
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
        
        # Check for existing requests by current user
        from sqlmodel import select
        from .models.media_request import MediaRequest, MediaType, RequestStatus
        
        # Get all request IDs for this user and these items
        request_query = select(MediaRequest).where(
            MediaRequest.user_id == current_user.id,
            MediaRequest.tmdb_id.in_([item['id'] for item in all_credits])
        )
        user_requests = session.exec(request_query).all()
        
        # Create a lookup for requests by tmdb_id and media_type
        request_lookup = {}
        for req in user_requests:
            key = (req.tmdb_id, req.media_type.value)
            request_lookup[key] = req
        
        # Add status to items
        for item in all_credits:
            # Check Plex status
            if item['media_type'] == 'movie':
                plex_status = movie_status.get(item['id'], 'available')
                item['in_plex'] = plex_status == 'in_plex'
            else:
                plex_status = tv_status.get(item['id'], 'available')
                item['in_plex'] = plex_status == 'in_plex'
            
            # Check request status
            request_key = (item['id'], item['media_type'])
            if request_key in request_lookup:
                req = request_lookup[request_key]
                if req.status == RequestStatus.PENDING:
                    item['status'] = 'requested_pending'
                elif req.status == RequestStatus.APPROVED:
                    item['status'] = 'requested_approved'
                elif req.status == RequestStatus.AVAILABLE:
                    item['status'] = 'in_plex'
                elif req.status == RequestStatus.REJECTED:
                    item['status'] = 'requested_rejected'
                else:
                    item['status'] = 'available'
            elif item['in_plex']:
                item['status'] = 'in_plex'
            else:
                item['status'] = 'available'
        
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