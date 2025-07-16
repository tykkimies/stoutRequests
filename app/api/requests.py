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
    global_context = get_global_template_context(current_user)
    # Merge contexts, with explicit context taking precedence
    merged_context = {**global_context, **context}
    return templates.TemplateResponse(template_name, merged_context)


class CreateRequestData(BaseModel):
    tmdb_id: int
    media_type: str
    title: str
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    release_date: Optional[str] = None

@router.post("/create")
async def create_request(
    tmdb_id: int = Form(...),
    media_type: str = Form(...),
    title: str = Form(...),
    overview: str = Form(""),
    poster_path: str = Form(""),
    release_date: str = Form(""),
    request_type: str = Form(""),  # For TV shows: complete, season, episode
    season_number: Optional[int] = Form(None),  # For season-specific requests
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
async def unified_requests(
    request: Request,
    current_user: User = Depends(get_current_user_flexible),
    session: Session = Depends(get_session)
):
    """Unified requests page with visibility controls"""
    try:
        # Get visibility settings
        visibility_config = SettingsService.get_request_visibility_config(session)
        
        # Determine what requests to show based on user permissions and settings
        user_lookup = {}  # Dictionary to store user info by request ID
        
        from ..core.permissions import is_user_admin
        if is_user_admin(current_user, session):
            # Admins always see all requests
            statement = select(MediaRequest, User).join(
                User, MediaRequest.user_id == User.id
            ).order_by(MediaRequest.created_at.desc())
            results = session.exec(statement).all()
            
            requests_with_users = []
            for media_request, user in results:
                user_lookup[media_request.id] = user
                requests_with_users.append(media_request)
                
        elif visibility_config['can_view_all_requests']:
            # Regular users can see all requests if setting is enabled
            if visibility_config['can_view_request_user']:
                # Show user info if enabled
                statement = select(MediaRequest, User).join(
                    User, MediaRequest.user_id == User.id
                ).order_by(MediaRequest.created_at.desc())
                results = session.exec(statement).all()
                
                requests_with_users = []
                for media_request, user in results:
                    user_lookup[media_request.id] = user
                    requests_with_users.append(media_request)
            else:
                # Hide user info - just get requests without user data
                statement = select(MediaRequest).order_by(MediaRequest.created_at.desc())
                requests_with_users = session.exec(statement).all()
        else:
            # Regular users can only see their own requests
            statement = select(MediaRequest).where(
                MediaRequest.user_id == current_user.id
            ).order_by(MediaRequest.created_at.desc())
            requests_with_users = session.exec(statement).all()
            
            # Add current user info for their own requests
            for media_request in requests_with_users:
                user_lookup[media_request.id] = current_user
        
        return create_template_response(
            "requests.html",
            {
                "request": request, 
                "requests": requests_with_users, 
                "current_user": current_user,
                "user_lookup": user_lookup,
                "show_request_user": is_user_admin(current_user, session) or visibility_config['can_view_request_user'],
                "can_view_all_requests": is_user_admin(current_user, session) or visibility_config['can_view_all_requests']
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
async def approve_request(
    request_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
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
    
    
    # Content negotiation - check if this is an HTMX request
    if request.headers.get("HX-Request"):
        # Check if this came from media detail page (has different target)
        hx_target = request.headers.get("HX-Target", "")
        print(f"🔍 APPROVE: HTMX Target received: '{hx_target}' (length: {len(hx_target)})")
        print(f"🔍 APPROVE: Target comparison: '{hx_target}' == 'request-section' ? {hx_target == 'request-section'}")
        if hx_target == "request-section":
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
            # From recent requests horizontal - update just the status badge
            return HTMLResponse(f'''
            <div class="ml-2 flex-shrink-0" id="status-badge-{media_request.id}">
                <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
                    ✓ Approved
                </span>
            </div>
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
async def reject_request(
    request_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
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
        if hx_target == "request-section":
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
            # From recent requests horizontal - update just the status badge
            return HTMLResponse(f'''
            <div class="ml-2 flex-shrink-0" id="status-badge-{media_request.id}">
                <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">
                    ✗ Rejected
                </span>
            </div>
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
    
    return {"message": "Request marked as available"}


@router.delete("/{request_id}/delete")
async def delete_request(
    request_id: int,
    current_user: User = Depends(get_current_user_flexible),
    session: Session = Depends(get_session)
):
    """Delete a media request (admin or request owner only)"""
    statement = select(MediaRequest).where(MediaRequest.id == request_id)
    media_request = session.exec(statement).first()
    
    if not media_request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    # Check permissions: admin or request owner
    from ..core.permissions import is_user_admin
    if not is_user_admin(current_user, session) and media_request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this request")
    
    # Delete the request
    session.delete(media_request)
    session.commit()
    
    return {"message": "Request deleted successfully"}


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