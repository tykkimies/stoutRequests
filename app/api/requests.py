from fastapi import APIRouter, Depends, HTTPException, Request, Body
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel
from fastapi import Form
from ..core.database import get_session
from ..core.template_context import get_global_template_context
from ..models.user import User
from ..models.media_request import MediaRequest, MediaType, RequestStatus
from ..api.auth import get_current_user_flexible, get_current_admin_user_flexible
from ..core.permission_decorators import (
    require_permission, require_any_permission, check_request_permissions, 
    check_media_type_permission
)
from ..models.role import PermissionFlags
from ..services.tmdb_service import TMDBService
from ..services.radarr_service import RadarrService
from ..services.sonarr_service import SonarrService
from ..services.settings_service import build_app_url
from ..services.settings_service import SettingsService
from ..services.permissions_service import PermissionsService

router = APIRouter(prefix="/requests", tags=["requests"])
templates = Jinja2Templates(directory="app/templates")


def create_template_response(template_name: str, context: dict):
    """Create a template response with global context included"""
    current_user = context.get('current_user')
    request = context.get('request')
    global_context = get_global_template_context(current_user, request)
    # Merge contexts, with explicit context taking precedence
    merged_context = {**global_context, **context}
    print(f"🔧 [REQUESTS API] Template: {template_name}")
    print(f"🔧 [REQUESTS API] Global context base_url: '{global_context.get('base_url', 'MISSING')}'")
    print(f"🔧 [REQUESTS API] Final merged context base_url: '{merged_context.get('base_url', 'MISSING')}'")
    return templates.TemplateResponse(template_name, merged_context)


class CreateRequestData(BaseModel):
    tmdb_id: int
    media_type: str
    title: str
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    release_date: Optional[str] = None


async def integrate_with_services(media_request: MediaRequest, session: Session) -> Optional[Dict]:
    """
    Automatically send approved requests to Radarr/Sonarr
    Returns integration result or None if no service configured
    """
    import asyncio
    
    try:
        if media_request.media_type == MediaType.MOVIE:
            # Send to Radarr
            from ..services.radarr_service import RadarrService
            
            radarr = RadarrService(session)
            if not radarr.base_url or not radarr.api_key:
                print(f"⚠️ Radarr not configured, skipping integration for movie request {media_request.id}")
                return None
            
            # Check if integration is disabled
            if radarr.instance and not radarr.instance.get_settings().get('enable_integration', True):
                print(f"⚠️ Radarr integration disabled, skipping integration for movie request {media_request.id}")
                return None
            
            print(f"🎬 Sending movie '{media_request.title}' (TMDB: {media_request.tmdb_id}) to Radarr...")
            print(f"🔍 Radarr service instance settings available: {radarr.instance.get_settings() if radarr.instance else 'No instance'}")
            
            # Add a timeout to prevent hanging
            try:
                result = await asyncio.wait_for(
                    radarr.add_movie(
                        tmdb_id=media_request.tmdb_id,
                        user_id=media_request.user_id
                    ),
                    timeout=30.0
                )
                
                if result:
                    return {
                        'service': 'Radarr',
                        'service_id': result.get('id'),
                        'title': result.get('title', media_request.title)
                    }
                else:
                    print(f"❌ Failed to add movie to Radarr: {media_request.title}")
                    return None
            except asyncio.TimeoutError:
                print(f"⏰ Radarr integration timeout for request {media_request.id}")
                return None
                
        elif media_request.media_type == MediaType.TV:
            # Send to Sonarr
            from ..services.sonarr_service import SonarrService
            
            sonarr = SonarrService(session)
            if not sonarr.base_url or not sonarr.api_key:
                print(f"⚠️ Sonarr not configured, skipping integration for TV request {media_request.id}")
                return None
            
            # Check if integration is disabled
            if sonarr.instance and not sonarr.instance.get_settings().get('enable_integration', True):
                print(f"⚠️ Sonarr integration disabled, skipping integration for TV request {media_request.id}")
                return None
            
            print(f"📺 Sending TV series '{media_request.title}' (TMDB: {media_request.tmdb_id}) to Sonarr...")
            print(f"🔍 Sonarr service instance settings available: {sonarr.instance.get_settings() if sonarr.instance else 'No instance'}")
            
            # Determine monitoring based on request type
            monitor_type = 'all'
            season_numbers = None
            episode_numbers = None
            
            if media_request.is_episode_request and media_request.season_number and media_request.episode_number:
                # This is an episode-specific request
                monitor_type = 'specificEpisodes'
                season_numbers = [media_request.season_number]
                episode_numbers = {media_request.season_number: [media_request.episode_number]}
                print(f"📺 Episode-specific request: monitoring S{media_request.season_number:02d}E{media_request.episode_number:02d}")
            elif media_request.is_season_request and media_request.season_number:
                # This is a season-specific request
                monitor_type = 'specificSeasons'
                season_numbers = [media_request.season_number]
                print(f"📺 Season-specific request: monitoring season {media_request.season_number}")
            else:
                print(f"📺 Complete series request: monitoring all seasons")
            
            # Add a timeout to prevent hanging
            try:
                result = await asyncio.wait_for(
                    sonarr.add_series(
                        tmdb_id=media_request.tmdb_id,
                        user_id=media_request.user_id,
                        monitor_type=monitor_type,
                        season_numbers=season_numbers,
                        episode_numbers=episode_numbers
                    ),
                    timeout=30.0
                )
                
                if result:
                    return {
                        'service': 'Sonarr',
                        'service_id': result.get('id'),
                        'title': result.get('title', media_request.title)
                    }
                else:
                    print(f"❌ Failed to add TV series to Sonarr: {media_request.title}")
                    return None
            except asyncio.TimeoutError:
                print(f"⏰ Sonarr integration timeout for request {media_request.id}")
                return None
        
        return None
        
    except Exception as e:
        print(f"❌ Error integrating request {media_request.id} with services: {e}")
        import traceback
        traceback.print_exc()
        return None

@router.post("/create")
async def create_request(
    tmdb_id: int = Form(...),
    media_type: str = Form(...),
    title: str = Form(...),
    overview: str = Form(""),
    poster_path: str = Form(""),
    release_date: str = Form(""),
    request_type: str = Form(""),  # For TV shows: complete, season, episode, granular
    season_number: Optional[int] = Form(None),  # For season-specific requests
    selected_seasons: Optional[str] = Form(None),  # JSON string for granular requests
    selected_episodes: Optional[str] = Form(None),  # JSON string for granular requests  
    request_source: str = Form("main"),  # "main" for main media, "similar_recommended" for cards
    current_user: User = Depends(get_current_user_flexible),
    session: Session = Depends(get_session)
):
    """Create a new media request from HTMX form POST"""

    if not all([tmdb_id, media_type, title]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    # Initialize permissions service
    permissions_service = PermissionsService(session)
    
    # Check if user can request this media type
    if not permissions_service.can_request_media_type(current_user.id, media_type):
        return HTMLResponse(
            f'''<div class="inline-flex items-center px-3 py-2 border border-red-300 text-sm leading-4 font-medium rounded-md text-red-700 bg-red-50">
                <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                </svg>
                Not permitted to request {media_type}s
            </div>'''
        )
    
    # Check request limits
    can_request, reason = permissions_service.can_make_request(current_user.id)
    if not can_request:
        return HTMLResponse(
            f'''<div class="inline-flex items-center px-3 py-2 border border-orange-300 text-sm leading-4 font-medium rounded-md text-orange-700 bg-orange-50">
                <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                </svg>
                {reason}
            </div>'''
        )

    # Enhanced request checking for TV shows
    statement = select(MediaRequest).where(
        MediaRequest.tmdb_id == tmdb_id,
        MediaRequest.media_type == MediaType(media_type),
        MediaRequest.user_id == current_user.id
    )
    existing_requests = session.exec(statement).all()
    
    # For TV shows, check if this conflicts with existing requests
    if existing_requests and media_type == 'tv':
        # Check if user already requested the complete series
        complete_request = next((req for req in existing_requests if not req.is_season_request), None)
        if complete_request:
            return HTMLResponse(
                f'''<div class="inline-flex items-center px-3 py-2 border border-yellow-300 text-sm leading-4 font-medium rounded-md text-yellow-700 bg-yellow-50">
                    <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                    </svg>
                    Complete Series Already Requested
                </div>'''
            )
        
        # If requesting complete series but partial requests exist, allow it (will supersede partials)
        if not season_number:
            # This is a complete series request - it's allowed even with existing partial requests
            pass
        else:
            # Check if this specific season is already requested
            season_request = next((req for req in existing_requests 
                                 if req.is_season_request and req.season_number == season_number), None)
            if season_request:
                return HTMLResponse(
                    f'''<div class="inline-flex items-center px-3 py-2 border border-yellow-300 text-sm leading-4 font-medium rounded-md text-yellow-700 bg-yellow-50">
                        <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                        </svg>
                        Season {season_number} Already Requested
                    </div>'''
                )
    elif existing_requests and media_type == 'movie':
        # Movies are simpler - only one request per movie
        return HTMLResponse(
            f'''<div class="inline-flex items-center px-3 py-2 border border-yellow-300 text-sm leading-4 font-medium rounded-md text-yellow-700 bg-yellow-50">
                <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                </svg>
                Already Requested
            </div>'''
        )

    # Note: Removed slow Radarr/Sonarr checks during request creation

    # Handle granular TV requests
    granular_data = None
    if media_type == 'tv' and request_type == 'granular':
        try:
            import json
            granular_data = {
                'selected_seasons': json.loads(selected_seasons) if selected_seasons else [],
                'selected_episodes': json.loads(selected_episodes) if selected_episodes else {}
            }
            print(f"🔍 [GRANULAR] Processing granular request for TMDB: {tmdb_id}")
            print(f"🔍 [GRANULAR] Raw data - selected_seasons: {selected_seasons}")
            print(f"🔍 [GRANULAR] Raw data - selected_episodes: {selected_episodes}")
            print(f"🔍 [GRANULAR] Parsed data: {granular_data}")
            print(f"🔍 [GRANULAR] User: {current_user.username} (ID: {current_user.id})")
            print(f"🔍 [GRANULAR] Auto-approve enabled: {permissions_service.should_auto_approve(current_user.id, media_type)}")
            
            # Process granular requests (seasons and episodes)
            created_requests = []
            
            # Process selected seasons
            if granular_data['selected_seasons']:
                for season_num in granular_data['selected_seasons']:
                    season_num = int(season_num)
                    
                    # Check if this season is already requested
                    existing_season_req = session.exec(select(MediaRequest).where(
                        MediaRequest.tmdb_id == tmdb_id,
                        MediaRequest.media_type == MediaType.TV,
                        MediaRequest.user_id == current_user.id,
                        MediaRequest.season_number == season_num,
                        MediaRequest.is_season_request == True
                    )).first()
                    
                    if existing_season_req:
                        continue  # Skip already requested seasons
                    
                    # Create season request
                    season_request = MediaRequest(
                        user_id=current_user.id,
                        tmdb_id=tmdb_id,
                        media_type=MediaType.TV,
                        title=f"{title} - Season {season_num}",
                        overview=overview,
                        poster_path=poster_path,
                        release_date=release_date,
                        season_number=season_num,
                        is_season_request=True,
                        status=RequestStatus.APPROVED if permissions_service.should_auto_approve(current_user.id, media_type) else RequestStatus.PENDING,
                        approved_by=current_user.id if permissions_service.should_auto_approve(current_user.id, media_type) else None,
                        approved_at=datetime.utcnow() if permissions_service.should_auto_approve(current_user.id, media_type) else None
                    )
                    session.add(season_request)
                    created_requests.append(season_request)
                    print(f"🔍 [GRANULAR] Created season request: S{season_num} - Status: {season_request.status.value}")
            
            # Process selected episodes
            if granular_data['selected_episodes']:
                for season_num_str, episode_numbers in granular_data['selected_episodes'].items():
                    season_num = int(season_num_str)
                    
                    for episode_num in episode_numbers:
                        episode_num = int(episode_num)
                        
                        # Check if this episode is already requested
                        existing_episode_req = session.exec(select(MediaRequest).where(
                            MediaRequest.tmdb_id == tmdb_id,
                            MediaRequest.media_type == MediaType.TV,
                            MediaRequest.user_id == current_user.id,
                            MediaRequest.season_number == season_num,
                            MediaRequest.episode_number == episode_num,
                            MediaRequest.is_episode_request == True
                        )).first()
                        
                        if existing_episode_req:
                            continue  # Skip already requested episodes
                        
                        # Create episode request
                        episode_request = MediaRequest(
                            user_id=current_user.id,
                            tmdb_id=tmdb_id,
                            media_type=MediaType.TV,
                            title=f"{title} - S{season_num:02d}E{episode_num:02d}",
                            overview=overview,
                            poster_path=poster_path,
                            release_date=release_date,
                            season_number=season_num,
                            episode_number=episode_num,
                            is_episode_request=True,
                            status=RequestStatus.APPROVED if permissions_service.should_auto_approve(current_user.id, media_type) else RequestStatus.PENDING,
                            approved_by=current_user.id if permissions_service.should_auto_approve(current_user.id, media_type) else None,
                            approved_at=datetime.utcnow() if permissions_service.should_auto_approve(current_user.id, media_type) else None
                        )
                        session.add(episode_request)
                        created_requests.append(episode_request)
                        print(f"🔍 [GRANULAR] Created episode request: S{season_num:02d}E{episode_num:02d} - Status: {episode_request.status.value}")
            
            # Commit all requests
            if created_requests:
                session.commit()
                
                # For approved requests, integrate with services ONCE with consolidated data
                approved_requests = [r for r in created_requests if r.status == RequestStatus.APPROVED]
                print(f"🔍 [GRANULAR] Total created requests: {len(created_requests)}")
                print(f"🔍 [GRANULAR] Approved requests: {len(approved_requests)}")
                
                if approved_requests:
                    # Coordinate Sonarr integration - send one consolidated request
                    season_numbers = set()
                    episode_numbers = {}
                    
                    for req in approved_requests:
                        if req.is_season_request and req.season_number:
                            season_numbers.add(req.season_number)
                            print(f"🔍 [GRANULAR] Added season {req.season_number} to Sonarr request")
                        elif req.is_episode_request and req.season_number and req.episode_number:
                            if req.season_number not in episode_numbers:
                                episode_numbers[req.season_number] = []
                            episode_numbers[req.season_number].append(req.episode_number)
                            print(f"🔍 [GRANULAR] Added episode S{req.season_number:02d}E{req.episode_number:02d} to Sonarr request")
                    
                    print(f"🔍 [GRANULAR] Final consolidated data - Seasons: {list(season_numbers)}, Episodes: {episode_numbers}")
                    
                    # Send consolidated request to Sonarr
                    if season_numbers or episode_numbers:
                        from ..services.sonarr_service import SonarrService
                        sonarr = SonarrService(session)
                        
                        print(f"🔍 [GRANULAR] Sonarr service - URL: {sonarr.base_url}, API Key: {'***' + (sonarr.api_key[-4:] if sonarr.api_key else 'None')}")
                        
                        if sonarr.base_url and sonarr.api_key:
                            print(f"📺 [GRANULAR] Sending consolidated granular request to Sonarr for TMDB: {tmdb_id}")
                            print(f"🔍 [GRANULAR] Seasons: {list(season_numbers)}, Episodes: {episode_numbers}")
                            
                            try:
                                # Determine monitoring type
                                if episode_numbers and not season_numbers:
                                    monitor_type = 'specificEpisodes'
                                    season_nums = list(episode_numbers.keys())
                                    print(f"🔍 [GRANULAR] Monitor type: specificEpisodes, seasons: {season_nums}")
                                elif season_numbers and not episode_numbers:
                                    monitor_type = 'specificSeasons' 
                                    season_nums = list(season_numbers)
                                    print(f"🔍 [GRANULAR] Monitor type: specificSeasons, seasons: {season_nums}")
                                else:
                                    # Mixed request - episodes take precedence
                                    monitor_type = 'specificEpisodes'
                                    season_nums = list(set(list(season_numbers) + list(episode_numbers.keys())))
                                    print(f"🔍 [GRANULAR] Monitor type: specificEpisodes (mixed), seasons: {season_nums}")
                                
                                print(f"🔍 [GRANULAR] Calling sonarr.add_series with monitor_type={monitor_type}")
                                result = await sonarr.add_series(
                                    tmdb_id=tmdb_id,
                                    user_id=current_user.id,
                                    monitor_type=monitor_type,
                                    season_numbers=season_nums,
                                    episode_numbers=episode_numbers if episode_numbers else None
                                )
                                
                                if result:
                                    print(f"✅ [GRANULAR] Consolidated granular request integrated with Sonarr: {result.get('title')}")
                                else:
                                    print(f"❌ [GRANULAR] Failed to send consolidated granular request to Sonarr")
                            except Exception as e:
                                print(f"❌ [GRANULAR] Error sending consolidated request to Sonarr: {e}")
                                import traceback
                                traceback.print_exc()
                        else:
                            print(f"⚠️ [GRANULAR] Sonarr not configured, skipping integration for granular requests")
                    else:
                        print(f"⚠️ [GRANULAR] No approved seasons or episodes to send to Sonarr")
                
                # Count different types of requests
                season_requests = [r for r in created_requests if r.is_season_request]
                episode_requests = [r for r in created_requests if r.is_episode_request]
                
                # Build success message
                parts = []
                if season_requests:
                    parts.append(f"{len(season_requests)} season{'s' if len(season_requests) != 1 else ''}")
                if episode_requests:
                    parts.append(f"{len(episode_requests)} episode{'s' if len(episode_requests) != 1 else ''}")
                
                if parts:
                    message = f"Requested {' and '.join(parts)}!"
                    return HTMLResponse(f'''<div class="inline-flex items-center px-3 py-2 border border-green-300 text-sm leading-4 font-medium rounded-md text-green-700 bg-green-50">
                        <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path>
                        </svg>
                        {message}
                    </div>''')
            
            # No new requests were created
            return HTMLResponse('''<div class="inline-flex items-center px-3 py-2 border border-yellow-300 text-sm leading-4 font-medium rounded-md text-yellow-700 bg-yellow-50">
                <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                </svg>
                All selected content already requested
            </div>''')
            
        except Exception as e:
            print(f"❌ Error processing granular request: {e}")
            # Fall back to regular request processing

    # Determine initial status based on auto-approval
    initial_status = RequestStatus.PENDING
    approved_by = None
    approved_at = None
    
    if permissions_service.should_auto_approve(current_user.id, media_type):
        initial_status = RequestStatus.APPROVED
        approved_by = current_user.id
        approved_at = datetime.utcnow()

    # Create new request
    new_request = MediaRequest(
        user_id=current_user.id,
        tmdb_id=tmdb_id,
        media_type=MediaType(media_type),
        title=title,
        overview=overview,
        poster_path=poster_path,
        release_date=release_date,
        season_number=season_number,
        is_season_request=bool(season_number),
        status=initial_status,
        approved_by=approved_by,
        approved_at=approved_at
    )

    session.add(new_request)
    session.commit()
    
    # Increment user request count (only for pending requests)
    if initial_status == RequestStatus.PENDING:
        permissions_service.increment_user_request_count(current_user.id)
    
    # 🎬 NEW: Automatic Service Integration for Auto-Approved Requests
    if initial_status == RequestStatus.APPROVED:
        integration_result = await integrate_with_services(new_request, session)
        if integration_result:
            print(f"✅ Auto-approved request {new_request.id} integrated with {integration_result['service']}")
        else:
            print(f"⚠️ Auto-approved request {new_request.id} could not be integrated (services may not be configured)")

    # Return appropriate message based on initial status
    if initial_status == RequestStatus.APPROVED:
        message = "Auto-approved!"
        color_class = "blue"
    else:
        message = "Requested!"
        color_class = "green"
    
    # Determine status badge HTML based on the request status
    if initial_status == RequestStatus.PENDING:
        badge_html = '''<span class="bg-yellow-600 text-white px-3 py-1 rounded-full text-sm font-medium">
            ⏳ Request Pending
        </span>'''
    else:  # APPROVED
        badge_html = '''<span class="bg-blue-600 text-white px-3 py-1 rounded-full text-sm font-medium">
            ✓ Request Approved
        </span>'''
    
    # Prepare out-of-band updates for any cards that might need refreshing
    card_updates = ""
    
    # If this request came from the similar/recommended section, trigger a refresh
    # We'll use a JavaScript trigger to refresh status badges on the page
    script_trigger = '''
    <script>
        // Trigger refresh of all status badges on the page
        document.body.dispatchEvent(new CustomEvent('refreshStatusBadges', {
            detail: { 
                updatedItemId: ''' + str(tmdb_id) + ''',
                newStatus: "''' + ("PENDING" if initial_status == RequestStatus.PENDING else "APPROVED") + '''"
            }
        }));
    </script>
    '''
    
    # Build the main response message
    response_html = f'''<div class="inline-flex items-center px-3 py-2 border border-{color_class}-300 text-sm leading-4 font-medium rounded-md text-{color_class}-700 bg-{color_class}-50">
        <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path>
        </svg>
        {message}
    </div>'''
    
    # Only add OOB updates for main media requests
    if request_source == "main":
        response_html += f'''
        <div hx-swap-oob="innerHTML:#request-status-badge">
            {badge_html}
        </div>
        <div hx-swap-oob="innerHTML:#request-section">
            <div class="bg-black bg-opacity-50 rounded-lg p-6 mt-6">
                <div class="text-green-400 text-center">
                    <svg class="w-8 h-8 mx-auto mb-2" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path>
                    </svg>
                    <p class="font-semibold">Request submitted successfully!</p>
                    <p class="text-sm text-gray-300 mt-1">{message}</p>
                </div>
            </div>
        </div>'''
    
    # Always add the script trigger for similar/recommended card updates
    response_html += script_trigger
    
    return HTMLResponse(response_html)



@router.get("/", response_class=HTMLResponse)
@router.get("", response_class=HTMLResponse)  # Handle both with and without trailing slash
async def unified_requests(
    request: Request,
    status: Optional[str] = None,
    media_type: Optional[str] = None,
    page: int = 1,
    limit: int = 24,
    current_user: User = Depends(get_current_user_flexible),
    session: Session = Depends(get_session)
):
    """Unified requests page with visibility controls"""
    try:
        # Get user's specific permissions directly from PermissionsService
        from ..services.permissions_service import PermissionsService
        from ..models.user_permissions import UserPermissions
        
        permissions_service = PermissionsService(session)
        user_perms_obj = permissions_service.get_user_permissions(current_user.id)
        custom_perms = user_perms_obj.get_custom_permissions() if user_perms_obj else {}
        
        # Determine what requests to show based on user permissions
        user_lookup = {}  # Dictionary to store user info by request ID
        
        from ..core.permissions import is_user_admin
        user_is_admin = is_user_admin(current_user, session)
        
        # Check user's specific viewing permissions
        can_view_all_requests = user_is_admin or custom_perms.get('can_view_other_users_requests', False)
        can_view_request_user = user_is_admin or custom_perms.get('can_see_requester_username', False)
        
        # Build query parameters once
        def build_base_query(include_user=True, include_status_filter=True, include_media_filter=True):
            if user_is_admin or (can_view_all_requests and can_view_request_user):
                if include_user:
                    query = select(MediaRequest, User).join(User, MediaRequest.user_id == User.id)
                else:
                    query = select(MediaRequest)
            elif can_view_all_requests:
                query = select(MediaRequest)
            else:
                # Regular users can only see their own requests
                query = select(MediaRequest).where(MediaRequest.user_id == current_user.id)
            
            # Apply filters
            if include_status_filter and status and status != 'all':
                try:
                    status_enum = RequestStatus(status.upper())
                    query = query.where(MediaRequest.status == status_enum)
                except ValueError:
                    pass
            
            if include_media_filter and media_type and media_type != 'all':
                try:
                    media_type_enum = MediaType(media_type.lower())
                    query = query.where(MediaRequest.media_type == media_type_enum)
                except ValueError:
                    pass
            
            return query.order_by(MediaRequest.created_at.desc())
        
        # Get total count for pagination
        count_statement = build_base_query(include_user=False)
        total_requests = len(session.exec(count_statement).all())
        
        # Apply pagination
        offset = (page - 1) * limit
        statement = build_base_query(include_user=True).offset(offset).limit(limit)
        
        user_lookup = {}
        requests_with_users = []
        
        if user_is_admin or (can_view_all_requests and can_view_request_user):
            # Query returns both MediaRequest and User
            results = session.exec(statement).all()
            for media_request, user in results:
                user_lookup[media_request.id] = user
                requests_with_users.append(media_request)
        else:
            # Query returns only MediaRequest
            requests_with_users = session.exec(statement).all()
            
            # Add current user info for their own requests if needed
            if not can_view_all_requests:
                for media_request in requests_with_users:
                    user_lookup[media_request.id] = current_user
        
        # Calculate pagination info
        total_pages = (total_requests + limit - 1) // limit
        has_next = page < total_pages
        has_prev = page > 1
        
        # Check if this is an HTMX request for fragments
        hx_target = request.headers.get("HX-Target", "")
        if request.headers.get("HX-Request") and hx_target in ["requests-content", "main-content"]:
            template_name = "components/main_content.html" if hx_target == "main-content" else "components/requests_content.html"
            
            # Get all requests for count calculations (reuse query builder)
            count_query = build_base_query(include_user=False, include_status_filter=False, include_media_filter=True)
            all_requests_for_counts = session.exec(count_query).all()
            
            # Return only the fragment
            return create_template_response(
                template_name,
                {
                    "request": request, 
                    "requests": requests_with_users, 
                    "all_requests_for_counts": all_requests_for_counts,
                    "current_user": current_user,
                    "user_lookup": user_lookup,
                    "user_is_admin": user_is_admin,
                    "show_request_user": can_view_request_user,
                    "can_view_all_requests": can_view_all_requests,
                    "current_status_filter": status or 'all',
                    "current_media_type_filter": media_type or 'all',
                    "current_page": page,
                    "total_pages": total_pages,
                    "has_next": has_next,
                    "has_prev": has_prev,
                    "total_requests": total_requests
                }
            )
        else:
            # Return full page
            return create_template_response(
                "requests.html",
                {
                    "request": request, 
                    "requests": requests_with_users, 
                    "current_user": current_user,
                    "user_lookup": user_lookup,
                    "user_is_admin": user_is_admin,
                    "show_request_user": can_view_request_user,
                    "can_view_all_requests": can_view_all_requests,
                    "current_status_filter": status or 'all',
                    "current_media_type_filter": media_type or 'all',
                    "current_page": page,
                    "total_pages": total_pages,
                    "has_next": has_next,
                    "has_prev": has_prev,
                    "total_requests": total_requests
                }
            )
        
    except Exception as e:
        print(f"Error in unified_requests: {e}")
        # Fallback to user's own requests
        statement = select(MediaRequest).where(MediaRequest.user_id == current_user.id).order_by(MediaRequest.created_at.desc())
        requests = session.exec(statement).all()
        
        # Create fallback user lookup
        user_lookup = {}
        for media_request in requests:
            user_lookup[media_request.id] = current_user
        
        return create_template_response(
            "requests.html",
            {
                "request": request, 
                "requests": requests, 
                "current_user": current_user,
                "user_lookup": user_lookup,
                "user_is_admin": False,  # In error case, default to False for safety
                "show_request_user": False,
                "can_view_all_requests": False
            }
        )


@router.get("/legacy", response_class=HTMLResponse)
async def my_requests_legacy(
    request: Request,
    current_user: User = Depends(get_current_user_flexible),
    session: Session = Depends(get_session)
):
    """Get user's requests (legacy endpoint - redirects to unified)"""
    # Redirect to unified endpoint
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=build_app_url("/requests"), status_code=302)






@router.post("/{request_id}/approve")
@require_permission(PermissionFlags.ADMIN_APPROVE_REQUESTS)
async def approve_request(
    request_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_flexible),
    session: Session = Depends(get_session)
):
    """Approve a media request"""
    statement = select(MediaRequest).where(MediaRequest.id == request_id)
    media_request = session.exec(statement).first()
    
    if not media_request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    # Track if this was previously pending to update user count
    was_pending = media_request.status == RequestStatus.PENDING
    
    media_request.status = RequestStatus.APPROVED
    media_request.approved_by = current_user.id
    media_request.approved_at = datetime.utcnow()
    
    # Decrement user request count if it was pending
    if was_pending:
        permissions_service = PermissionsService(session)
        permissions_service.decrement_user_request_count(media_request.user_id)
    
    session.add(media_request)
    session.commit()
    
    # 🎬 NEW: Automatic Service Integration
    # Send approved request to Radarr/Sonarr if services are configured
    if was_pending:  # Only integrate newly approved requests, not already approved ones
        integration_result = await integrate_with_services(media_request, session)
        if integration_result:
            print(f"✅ Successfully integrated request {request_id} with {integration_result['service']}")
        else:
            print(f"⚠️ Could not integrate request {request_id} with services (may not be configured)")
    
    # Content negotiation - check if this is an HTMX request
    if request.headers.get("HX-Request"):
        # Check if this came from media detail page (has different target)
        hx_target = request.headers.get("HX-Target", "")
        print(f"🔍 APPROVE: HTMX Target received: '{hx_target}' (length: {len(hx_target)})")
        print(f"🔍 APPROVE: Target comparison: '{hx_target}' == 'request-section' ? {hx_target == 'request-section'}")
        
        if hx_target in ["requests-content", "main-content"]:
            # From requests list page - return updated content with current filters
            status_filter = request.query_params.get('status', 'all')
            media_type_filter = request.query_params.get('media_type', 'all')
            
            # Call unified_requests to get the updated content
            return await unified_requests(request, status_filter, media_type_filter, 1, 24, current_user, session)
            
        elif hx_target == "request-section":
            # From media detail page - return updated request section
            
            # Check if user has admin permissions using unified function
            from ..core.permissions import is_user_admin
            user_is_admin = is_user_admin(current_user, session)
            
            # Create context for the updated request section
            context = {
                "request": request,
                "request_status": "approved",
                "has_complete_request": not media_request.is_season_request,
                "has_partial_requests": media_request.is_season_request,
                "user_partial_requests": [media_request] if media_request.is_season_request else [],
                "integration_message": integration_message,
                "media_type": media_request.media_type.value,
                "current_user": current_user,
                "user_is_admin": user_is_admin,
                "existing_request": media_request,
                "is_in_plex": False
            }
            
            # Return the request section with out-of-band status badge update
            from fastapi.templating import Jinja2Templates
            from ..core.template_context import get_global_template_context
            templates = Jinja2Templates(directory="app/templates")
            
            # Get the global context and render the component
            global_context = get_global_template_context()
            merged_context = {**global_context, **context}
            
            # Render the request section component
            request_section_html = templates.get_template("components/request_section.html").render(merged_context)
            
            # Return HTML with out-of-band swap for status badge
            return HTMLResponse(f'''
            <div hx-swap-oob="innerHTML:#request-status-badge">
                <span class="bg-blue-600 text-white px-3 py-1 rounded-full text-sm font-medium">
                    ✓ Request Approved
                </span>
            </div>
            {request_section_html}
            ''')
        elif hx_target == "request-status-badge":
            # From media detail page badge - just update the badge
            return HTMLResponse(f'''
            <span class="bg-blue-600 text-white px-3 py-1 rounded-full text-sm font-medium">
                ✓ Request Approved
            </span>
            ''')
        elif hx_target.startswith("status-badge-"):
            # From recent requests horizontal - update the status badge and hide admin actions
            return HTMLResponse(f'''
            <div class="ml-2 flex-shrink-0" id="status-badge-{media_request.id}">
                <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
                    ✓ Approved
                </span>
            </div>
            <div hx-swap-oob="outerHTML:#admin-actions-{media_request.id}"></div>
            ''')
        else:
            # From admin requests list - return status badge
            badge_text = "✓ Approved"
            badge_class = "bg-blue-100 text-blue-800"
                
            return HTMLResponse(f'''
            <div class="ml-2 flex-shrink-0" id="status-badge-{media_request.id}">
                <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium {badge_class}">
                    {badge_text}
                </span>
            </div>
            ''')
    else:
        # Regular API response
        return {"message": "Request approved"}


@router.post("/{request_id}/reject")
@require_permission(PermissionFlags.ADMIN_APPROVE_REQUESTS)
async def reject_request(
    request_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_flexible),
    session: Session = Depends(get_session)
):
    """Reject a media request"""
    statement = select(MediaRequest).where(MediaRequest.id == request_id)
    media_request = session.exec(statement).first()
    
    if not media_request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    # Track if this was previously pending to update user count
    was_pending = media_request.status == RequestStatus.PENDING
    
    media_request.status = RequestStatus.REJECTED
    media_request.approved_by = current_user.id
    media_request.approved_at = datetime.utcnow()
    
    session.add(media_request)
    session.commit()
    
    # Decrement user request count if it was pending
    if was_pending:
        permissions_service = PermissionsService(session)
        permissions_service.decrement_user_request_count(media_request.user_id)
    
    # Content negotiation - check if this is an HTMX request
    if request.headers.get("HX-Request"):
        # Check if this came from media detail page (has different target)
        hx_target = request.headers.get("HX-Target", "")
        print(f"🔍 REJECT: HTMX Target received: '{hx_target}' (length: {len(hx_target)})")
        print(f"🔍 REJECT: Target comparison: '{hx_target}' == 'request-section' ? {hx_target == 'request-section'}")
        
        if hx_target in ["requests-content", "main-content"]:
            # From requests list page - return updated content with current filters
            status_filter = request.query_params.get('status', 'all')
            media_type_filter = request.query_params.get('media_type', 'all')
            
            # Call unified_requests to get the updated content
            return await unified_requests(request, status_filter, media_type_filter, 1, 24, current_user, session)
            
        elif hx_target == "request-section":
            # From media detail page - return updated request section
            
            # Check if user has admin permissions using unified function
            from ..core.permissions import is_user_admin
            user_is_admin = is_user_admin(current_user, session)
            
            # Create context for the updated request section
            context = {
                "request": request,
                "request_status": "rejected",
                "has_complete_request": not media_request.is_season_request,
                "has_partial_requests": media_request.is_season_request,
                "user_partial_requests": [media_request] if media_request.is_season_request else [],
                "media_type": media_request.media_type.value,
                "current_user": current_user,
                "user_is_admin": user_is_admin,
                "existing_request": media_request,
                "is_in_plex": False
            }
            
            # Return the request section with out-of-band status badge update
            from fastapi.templating import Jinja2Templates
            from ..core.template_context import get_global_template_context
            templates = Jinja2Templates(directory="app/templates")
            
            # Get the global context and render the component
            global_context = get_global_template_context()
            merged_context = {**global_context, **context}
            
            # Render the request section component
            request_section_html = templates.get_template("components/request_section.html").render(merged_context)
            
            # Return HTML with out-of-band swap for status badge
            return HTMLResponse(f'''
            <div hx-swap-oob="innerHTML:#request-status-badge">
                <span class="bg-red-600 text-white px-3 py-1 rounded-full text-sm font-medium">
                    ✗ Request Rejected
                </span>
            </div>
            {request_section_html}
            ''')
        elif hx_target == "request-status-badge":
            # From media detail page badge - just update the badge
            return HTMLResponse(f'''
            <span class="bg-red-600 text-white px-3 py-1 rounded-full text-sm font-medium">
                ✗ Request Rejected
            </span>
            ''')
        elif hx_target.startswith("status-badge-"):
            # From recent requests horizontal - update the status badge and hide admin actions
            return HTMLResponse(f'''
            <div class="ml-2 flex-shrink-0" id="status-badge-{media_request.id}">
                <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">
                    ✗ Rejected
                </span>
            </div>
            <div hx-swap-oob="outerHTML:#admin-actions-{media_request.id}"></div>
            ''')
        else:
            # From admin requests list - return status badge
            return HTMLResponse(f'''
            <div class="ml-2 flex-shrink-0" id="status-badge-{media_request.id}">
                <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800">
                    ✗ Rejected
                </span>
            </div>
            ''')
    else:
        # Regular API response
        return {"message": "Request rejected"}


@router.post("/{request_id}/mark-available")
async def mark_as_available(
    request_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Mark a media request as available"""
    statement = select(MediaRequest).where(MediaRequest.id == request_id)
    media_request = session.exec(statement).first()
    
    if not media_request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    media_request.status = RequestStatus.AVAILABLE
    media_request.approved_by = current_user.id
    media_request.approved_at = datetime.utcnow()
    
    session.add(media_request)
    session.commit()
    
    # Content negotiation - check if this is an HTMX request
    if request.headers.get("HX-Request"):
        hx_target = request.headers.get("HX-Target", "")
        
        if hx_target in ["requests-content", "main-content"]:
            # From requests list page - return updated content with current filters
            status_filter = request.query_params.get('status', 'all')
            media_type_filter = request.query_params.get('media_type', 'all')
            
            # Call unified_requests to get the updated content
            return await unified_requests(request, status_filter, media_type_filter, 1, 24, current_user, session)
    
    return {"message": "Request marked as available"}


@router.delete("/{request_id}/delete")
async def delete_request(
    request_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_flexible),
    session: Session = Depends(get_session)
):
    """Delete a media request (admin or request owner only)"""
    try:
        statement = select(MediaRequest).where(MediaRequest.id == request_id)
        media_request = session.exec(statement).first()
        
        if not media_request:
            raise HTTPException(status_code=404, detail="Request not found")
        
        # Check permissions: admin, delete permission, or request owner
        permissions_service = PermissionsService(session)
        
        # Check if user can delete this request
        can_delete = (
            media_request.user_id == current_user.id or  # Owner can delete
            permissions_service.has_permission(current_user.id, PermissionFlags.ADMIN_DELETE_REQUESTS) or  # Delete permission
            permissions_service.has_permission(current_user.id, PermissionFlags.REQUEST_MANAGE_ALL)  # Manage all requests
        )
        
        if not can_delete:
            raise HTTPException(status_code=403, detail="Not authorized to delete this request")
        
        # Store filter values before deletion for potential HTMX response
        status_filter = request.query_params.get('status', 'all')
        media_type_filter = request.query_params.get('media_type', 'all')
        hx_target = request.headers.get("HX-Target", "")
        
        # Track if this was a pending request to update user count
        was_pending = media_request.status == RequestStatus.PENDING
        user_id = media_request.user_id
        
        # Delete the request
        session.delete(media_request)
        session.commit()
        
        # Decrement user request count if it was pending
        if was_pending:
            permissions_service = PermissionsService(session)
            permissions_service.decrement_user_request_count(user_id)
        
        print(f"✅ Successfully deleted request {request_id}")
        
        # Content negotiation - check if this is an HTMX request
        if request.headers.get("HX-Request"):
            # Use out-of-band swaps for ALL HTMX targets to avoid reloading content
            from fastapi.responses import HTMLResponse
            return HTMLResponse(f'''
                <div></div>
                <div hx-swap-oob="delete:#request-card-{request_id}"></div>
                <div hx-swap-oob="innerHTML:#success-message">
                    <div class="fixed top-4 right-4 bg-green-500 text-white px-4 py-2 rounded shadow-lg z-50" 
                         style="animation: fadeOut 3s forwards;">
                        ✅ Request deleted successfully
                    </div>
                </div>
            ''')
        
        return {"message": "Request deleted successfully"}
        
    except HTTPException:
        # Re-raise HTTP exceptions (404, 403)
        raise
    except Exception as e:
        print(f"❌ Error deleting request {request_id}: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete request: {str(e)}")


@router.get("/{request_id}/status-update", response_class=HTMLResponse)
async def get_request_status_update(
    request_id: int,
    current_user: User = Depends(get_current_user_flexible),
    session: Session = Depends(get_session)
):
    """Get updated request section HTML for HTMX updates"""
    statement = select(MediaRequest).where(MediaRequest.id == request_id)
    media_request = session.exec(statement).first()
    
    if not media_request:
        return HTMLResponse("")
    
    # Check if user has admin permissions using unified function
    from ..core.permissions import is_user_admin
    user_is_admin = is_user_admin(current_user, session)
    
    # Build context for the request section component
    context = {
        "request_status": media_request.status.value,
        "has_complete_request": not media_request.is_season_request,
        "has_partial_requests": media_request.is_season_request,
        "user_partial_requests": [media_request] if media_request.is_season_request else [],
        "media_type": media_request.media_type.value,
        "current_user": current_user,
        "user_is_admin": user_is_admin,
        "existing_request": media_request,
        "is_in_plex": False,
        "base_url": ""
    }
    
    return create_template_response("components/request_section.html", context)