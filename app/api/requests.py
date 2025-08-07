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
from ..models.service_instance import ServiceInstance
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
from ..services.instance_selection_service import InstanceSelectionService
from ..services.multi_instance_integration_service import integrate_with_multi_instance_services

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


async def create_template_response_with_instances(template_name: str, context: dict, session: Session = None):
    """Create a template response with instance data for multi-instance support"""
    current_user = context.get('current_user')
    media_type = context.get('media_type', context.get('current_media_type', 'movie'))
    requests = context.get('requests', [])
    
    # Get available instances for the user
    from ..main import get_user_instances_for_template
    available_instances = await get_user_instances_for_template(current_user, media_type)
    
    # Create instance lookup for requests that have service instances
    instance_lookup = {}
    if requests and session:
        from sqlmodel import select
        from ..models.service_instance import ServiceInstance
        
        # Get all unique instance IDs from requests
        instance_ids = {req.service_instance_id for req in requests if req.service_instance_id}
        
        if instance_ids:
            # Load all instances in one query
            statement = select(ServiceInstance).where(ServiceInstance.id.in_(instance_ids))
            instances = session.exec(statement).all()
            
            # Create lookup dictionary
            for instance in instances:
                instance_lookup[instance.id] = instance
    
    # Add instance data to context
    enhanced_context = {
        **context,
        'available_instances': available_instances,
        'instance_lookup': instance_lookup
    }
    
    print(f"🔧 [REQUESTS API MULTI_INSTANCE] Template: {template_name}")
    print(f"🔧 [REQUESTS API MULTI_INSTANCE] Media type: {media_type}")
    print(f"🔧 [REQUESTS API MULTI_INSTANCE] Available instances: {len(available_instances)}")
    if available_instances and current_user:
        print(f"🔧 [REQUESTS API MULTI_INSTANCE] User is admin: {current_user.is_admin if current_user else False}")
        print(f"🔧 [REQUESTS API MULTI_INSTANCE] Has multiple instances: {len(available_instances) > 1}")
    else:
        print(f"🔧 [REQUESTS API MULTI_INSTANCE] ❌ No instances available for user {current_user.username if current_user else 'None'}")
    
    return create_template_response(template_name, enhanced_context)


class CreateRequestData(BaseModel):
    tmdb_id: int
    media_type: str
    title: str
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    release_date: Optional[str] = None


async def integrate_with_services(media_request: MediaRequest, session: Session) -> Optional[Dict]:
    """
    Automatically send approved requests to Radarr/Sonarr using the specified service instance
    Returns integration result or None if no service configured
    """
    import asyncio
    from sqlmodel import select
    from ..models.service_instance import ServiceInstance
    
    print(f"\n🎬 ===== INTEGRATION CHAIN STARTING ===== 🎬")
    print(f"📊 Request ID: {media_request.id}")
    print(f"📊 Title: {media_request.title}")
    print(f"📊 Media Type: {media_request.media_type.value}")
    print(f"📊 TMDB ID: {media_request.tmdb_id}")
    print(f"📊 Service Instance ID: {media_request.service_instance_id}")
    print(f"📊 Quality Tier: {media_request.requested_quality_tier}")
    print(f"📊 User ID: {media_request.user_id}")
    print(f"📊 Season Request: {media_request.is_season_request}")
    print(f"📊 Episode Request: {media_request.is_episode_request}")
    if media_request.is_season_request and media_request.season_number:
        print(f"📊 Season Number: {media_request.season_number}")
    if media_request.is_episode_request and media_request.episode_number:
        print(f"📊 Episode Number: {media_request.episode_number}")
    
    # Get the specific service instance that was selected for this request
    if not media_request.service_instance_id:
        print(f"❌ INTEGRATION FAILED: No service instance specified for request {media_request.id}")
        print(f"🔍 This request does not have a service instance assigned")
        print(f"🔍 Multi-instance support requires a service instance to be selected")
        return None
    
    print(f"🔍 Loading service instance {media_request.service_instance_id} from database...")
    # Load the service instance
    statement = select(ServiceInstance).where(ServiceInstance.id == media_request.service_instance_id)
    service_instance = session.exec(statement).first()
    
    if not service_instance:
        print(f"❌ INTEGRATION FAILED: Service instance {media_request.service_instance_id} not found in database")
        return None
    
    print(f"✅ Found service instance: {service_instance.name}")
    print(f"📊 Instance Type: {service_instance.service_type.value}")
    print(f"📊 Instance URL: {service_instance.url}")
    print(f"📊 Instance Enabled: {service_instance.is_enabled}")
    print(f"📊 Instance Category: {service_instance.instance_category}")
    print(f"📊 API Key Present: {'✅' if service_instance.api_key else '❌'}")
    
    try:
        # Use the multi-instance integration service
        from ..services.multi_instance_integration_service import MultiInstanceIntegrationService
        
        print(f"🔧 Creating MultiInstanceIntegrationService...")
        integration_service = MultiInstanceIntegrationService(session)
        
        print(f"🔗 Starting integration for request {media_request.id} ({media_request.title}) with instance '{service_instance.name}'...")
        
        # Add a timeout to prevent hanging
        try:
            print(f"⏰ Starting integration with 30s timeout...")
            result = await asyncio.wait_for(
                integration_service.integrate_request(media_request),
                timeout=30.0
            )
            
            print(f"📡 Integration result received: {result}")
            
            if result:
                success_data = {
                    'service': f"{service_instance.service_type.value.title()} ({service_instance.name})",
                    'service_id': result.get('service_id'),
                    'title': result.get('title', media_request.title),
                    'instance_name': service_instance.name
                }
                print(f"✅ INTEGRATION SUCCESS: {success_data}")
                return success_data
            else:
                print(f"❌ INTEGRATION FAILED: No result returned from integration service for request {media_request.id}")
                return None
        except asyncio.TimeoutError:
            print(f"⏰ INTEGRATION TIMEOUT: 30s timeout exceeded for request {media_request.id} on instance '{service_instance.name}'")
            return None
        
    except Exception as e:
        print(f"❌ INTEGRATION EXCEPTION: Error integrating request {media_request.id} with services: {e}")
        import traceback
        print(f"🔍 Full stack trace:")
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
    # Multi-instance support
    service_instance_id: Optional[int] = Form(None),  # Specific instance to use
    quality_tier: str = Form("standard"),  # Quality tier requested ("standard", "4k", "hdr")
    current_user: User = Depends(get_current_user_flexible),
    session: Session = Depends(get_session)
):
    """Create a new media request from HTMX form POST"""

    if not all([tmdb_id, media_type, title]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    # Initialize services
    permissions_service = PermissionsService(session)
    instance_service = InstanceSelectionService(session)
    
    # Multi-instance support: Validate and select service instance
    selected_instance = None
    if service_instance_id:
        # User specified a particular instance - validate access
        if not await instance_service.validate_instance_access(
            current_user.id, service_instance_id, MediaType(media_type), quality_tier
        ):
            return HTMLResponse(
                f'''<div class="inline-flex items-center px-3 py-2 border border-red-300 text-sm leading-4 font-medium rounded-md text-red-700 bg-red-50">
                    <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                    </svg>
                    No access to selected service instance
                </div>'''
            )
        selected_instance = session.get(ServiceInstance, service_instance_id)
    else:
        # Auto-select best instance for user
        selected_instance = await instance_service.select_best_instance(
            current_user.id, MediaType(media_type), quality_tier
        )
        
    if not selected_instance:
        return HTMLResponse(
            f'''<div class="inline-flex items-center px-3 py-2 border border-red-300 text-sm leading-4 font-medium rounded-md text-red-700 bg-red-50">
                <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                </svg>
                No available service instances for this request type
            </div>'''
        )
    
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
                    
                    # Create season request with multi-instance support
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
                        approved_at=datetime.utcnow() if permissions_service.should_auto_approve(current_user.id, media_type) else None,
                        # Multi-instance fields
                        service_instance_id=selected_instance.id,
                        requested_quality_tier=quality_tier
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
                        
                        # Create episode request with multi-instance support
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
                            approved_at=datetime.utcnow() if permissions_service.should_auto_approve(current_user.id, media_type) else None,
                            # Multi-instance fields
                            service_instance_id=selected_instance.id,
                            requested_quality_tier=quality_tier
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

    # Create new request with multi-instance support
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
        approved_at=approved_at,
        # Multi-instance fields
        service_instance_id=selected_instance.id,
        requested_quality_tier=quality_tier
    )

    session.add(new_request)
    session.commit()
    
    # Increment user request count (only for pending requests)
    if initial_status == RequestStatus.PENDING:
        permissions_service.increment_user_request_count(current_user.id)
    
    # 🎬 NEW: Automatic Service Integration for Auto-Approved Requests (Multi-Instance)
    if initial_status == RequestStatus.APPROVED:
        integration_result = await integrate_with_multi_instance_services(new_request, session)
        if integration_result:
            print(f"✅ Auto-approved request {new_request.id} integrated with {integration_result['service']}")
        else:
            print(f"⚠️ Auto-approved request {new_request.id} could not be integrated (services may not be configured)")

    # Return appropriate message based on initial status
    if initial_status == RequestStatus.APPROVED:
        message = "Approved!"
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
        // Defer the status badge refresh to prevent blocking
        setTimeout(() => {
            document.body.dispatchEvent(new CustomEvent('refreshStatusBadges', {
                detail: { 
                    updatedItemId: ''' + str(tmdb_id) + ''',
                    newStatus: "''' + ("PENDING" if initial_status == RequestStatus.PENDING else "APPROVED") + '''"
                }
            }));
        }, 100);
    </script>
    '''
    
    # Special handling for multi-instance requests (from dropdowns) - return simple success message
    if request_source == "multi_instance":
        # Use the proper status values that the macro expects
        if initial_status == RequestStatus.APPROVED:
            computed_status = 'requested_approved'
            status_message = f"Request auto approved and sent to {selected_instance.name}!"
        else:
            computed_status = 'requested_pending'
            status_message = f"Request submitted to {selected_instance.name} and pending approval!"
        
        # Generate the proper status badges using the same logic as the macro
        if computed_status == 'requested_approved':
            button_badge = '<div class="w-full bg-blue-600/90 backdrop-blur-sm text-white px-2 py-1 rounded text-xs font-medium text-center">✓ Approved</div>'
            overlay_badge = '<span class="bg-blue-600/90 backdrop-blur-sm text-white px-2 py-1 rounded text-xs font-medium">Approved</span>'
        else:  # requested_pending
            button_badge = '<div class="w-full bg-yellow-600/90 backdrop-blur-sm text-white px-2 py-1 rounded text-xs font-medium text-center">⏳ Pending</div>'
            overlay_badge = '<span class="bg-yellow-600/90 backdrop-blur-sm text-white px-2 py-1 rounded text-xs font-medium">Pending</span>'
        
        # Return the badge that will replace the dropdown form
        return HTMLResponse(f'''
        {button_badge}
        
        <script>
            // Close the dropdown after successful request
            closeAllDropdowns();
            
            // Defer the badge update to prevent blocking
            setTimeout(() => {{
                // Update the top-left overlay if it exists and doesn't have an "In Plex" badge
                const cardElement = document.getElementById('media-card-{tmdb_id}');
                if (cardElement) {{
                    const topBadgeArea = cardElement.querySelector('.absolute.top-2.left-2');
                    if (topBadgeArea && !topBadgeArea.querySelector('.bg-green-600')) {{
                        topBadgeArea.innerHTML = `{overlay_badge}`;
                    }}
                }}
            }}, 50);
        </script>
        ''')
    
    # Build the main response message for non-multi-instance requests using consistent button style
    if initial_status == RequestStatus.APPROVED:
        response_html = '<div class="w-full bg-blue-600/90 backdrop-blur-sm text-white px-2 py-1 rounded text-xs font-medium text-center">✓ Approved</div>'
        overlay_badge = '<span class="bg-blue-600/90 backdrop-blur-sm text-white px-2 py-1 rounded text-xs font-medium">Approved</span>'
    else:  # PENDING
        response_html = '<div class="w-full bg-yellow-600/90 backdrop-blur-sm text-white px-2 py-1 rounded text-xs font-medium text-center">⏳ Pending</div>'
        overlay_badge = '<span class="bg-yellow-600/90 backdrop-blur-sm text-white px-2 py-1 rounded text-xs font-medium">Pending</span>'
    
    # Add overlay badge update script for non-multi-instance requests
    response_html += f'''
    <script>
        // Defer the badge update to prevent blocking
        setTimeout(() => {{
            // Update the top-left overlay badge for non-multi-instance requests
            const cardElement = document.getElementById('media-card-{tmdb_id}');
            if (cardElement) {{
                const topBadgeArea = cardElement.querySelector('.absolute.top-2.left-2');
                if (topBadgeArea && !topBadgeArea.querySelector('.bg-green-600')) {{
                    topBadgeArea.innerHTML = `{overlay_badge}`;
                }}
            }}
        }}, 50);
    </script>
    '''
    
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
            return await create_template_response_with_instances(
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
                },
                session
            )
        else:
            # Return full page
            return await create_template_response_with_instances(
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
                },
                session
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
        
        return await create_template_response_with_instances(
            "requests.html",
            {
                "request": request, 
                "requests": requests, 
                "current_user": current_user,
                "user_lookup": user_lookup,
                "user_is_admin": False,  # In error case, default to False for safety
                "show_request_user": False,
                "can_view_all_requests": False
            },
            session
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






@router.get("/{request_id}/quality-profiles", response_class=HTMLResponse)
@require_permission(PermissionFlags.ADMIN_APPROVE_REQUESTS)
async def get_request_quality_profiles(
    request_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_flexible),
    session: Session = Depends(get_session)
):
    """Get quality profiles for a request's service instance"""
    statement = select(MediaRequest).where(MediaRequest.id == request_id)
    media_request = session.exec(statement).first()
    
    if not media_request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if not media_request.service_instance_id:
        return HTMLResponse('<option value="">No service instance configured</option>')
    
    # Get the service instance
    instance_statement = select(ServiceInstance).where(ServiceInstance.id == media_request.service_instance_id)
    service_instance = session.exec(instance_statement).first()
    
    if not service_instance:
        return HTMLResponse('<option value="">Service instance not found</option>')
    
    try:
        # Get quality profiles from the service instance
        from ..services.multi_instance_integration_service import MultiInstanceIntegrationService
        integration_service = MultiInstanceIntegrationService(session)
        profiles = await integration_service.get_instance_quality_profiles(service_instance)
        
        if not profiles:
            return HTMLResponse('<option value="">No quality profiles available</option>')
        
        # Build options HTML
        options_html = '<option value="">Use default quality profile</option>'
        for profile in profiles:
            profile_name = profile.get('name', f'Profile {profile.get("id")}')
            profile_id = profile.get('id')
            options_html += f'<option value="{profile_id}">{profile_name}</option>'
        
        return HTMLResponse(options_html)
        
    except Exception as e:
        print(f"❌ Error getting quality profiles: {e}")
        return HTMLResponse('<option value="">Error loading profiles</option>')


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
    
    # Check for instance override in form data
    form_data = await request.form() if request.method == "POST" else {}
    instance_override = form_data.get("override_instance_id")
    if instance_override and instance_override.strip() and instance_override != "":
        try:
            # Update the service instance for this request
            new_instance_id = int(instance_override)
            old_instance_id = media_request.service_instance_id
            media_request.service_instance_id = new_instance_id
            print(f"🎯 Instance override: {old_instance_id} -> {new_instance_id}")
        except ValueError:
            print(f"⚠️ Invalid instance ID: {instance_override}")
    
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
        print(f"\n🚀 ===== APPROVAL -> INTEGRATION FLOW ===== 🚀")
        print(f"📊 Request ID: {request_id}")
        print(f"📊 Was Pending: {was_pending}")
        print(f"📊 Current Status: {media_request.status.value}")
        print(f"📊 Service Instance ID: {media_request.service_instance_id}")
        print(f"📊 Media Type: {media_request.media_type.value}")
        print(f"📊 Title: {media_request.title}")
        print(f"📊 TMDB ID: {media_request.tmdb_id}")
        print(f"📊 Approved By: {current_user.id} ({current_user.username})")
        print(f"📊 Approved At: {media_request.approved_at}")
        
        print(f"🔧 Calling integrate_with_services...")
        integration_result = await integrate_with_services(media_request, session)
        
        if integration_result:
            print(f"✅ APPROVAL INTEGRATION SUCCESS: Request {request_id} integrated with {integration_result['service']}")
            print(f"📊 Service ID: {integration_result.get('service_id')}")
            print(f"📊 Instance: {integration_result.get('instance_name')}")
        else:
            print(f"❌ APPROVAL INTEGRATION FAILED: Could not integrate request {request_id} with services")
            print(f"🔍 This could mean:")
            print(f"🔍   - Service instance not found or disabled")
            print(f"🔍   - API connection issues")
            print(f"🔍   - Configuration problems")
            print(f"🔍   - Media already exists in service")
            print(f"🔍   - Quality profile or root folder misconfiguration")
            print(f"🔍   - Network connectivity issues")
            print(f"🔍 Review the detailed logs above to identify the specific failure point")
    
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
            integration_message = "Request approved and sent to service" if integration_result else "Request approved (service integration failed)"
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
            if hx_target in ["requests-content", "main-content"]:
                # From requests list page - return updated content with current filters to update counts
                return await unified_requests(request, status_filter, media_type_filter, 1, 24, current_user, session)
            else:
                # Use out-of-band swaps for other targets
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