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

router = APIRouter(prefix="/requests", tags=["requests"])
templates = Jinja2Templates(directory="app/templates")


def create_template_response(template_name: str, context: dict):
    """Create a template response with global context included"""
    global_context = get_global_template_context()
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
    current_user: User = Depends(get_current_user_flexible),
    session: Session = Depends(get_session)
):
    """Create a new media request from HTMX form POST"""

    if not all([tmdb_id, media_type, title]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    # Check if already requested by this user
    statement = select(MediaRequest).where(
        MediaRequest.tmdb_id == tmdb_id,
        MediaRequest.media_type == MediaType(media_type),
        MediaRequest.user_id == current_user.id
    )
    existing_request = session.exec(statement).first()

    if existing_request:
        return HTMLResponse(
            f'''<div class="inline-flex items-center px-3 py-2 border border-yellow-300 text-sm leading-4 font-medium rounded-md text-yellow-700 bg-yellow-50">
                <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                </svg>
                Already Requested
            </div>'''
        )

    # Check Radarr/Sonarr
    try:
        if media_type == 'movie':
            radarr_service = RadarrService(session)
            if radarr_service.get_movie_by_tmdb_id(tmdb_id):
                return HTMLResponse(
                    f'''<div class="inline-flex items-center px-3 py-2 border border-blue-300 text-sm leading-4 font-medium rounded-md text-blue-700 bg-blue-50">
                        <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path>
                        </svg>
                        In Radarr
                    </div>'''
                )
        elif media_type == 'tv':
            sonarr_service = SonarrService(session)
            if sonarr_service.get_series_by_tmdb_id(tmdb_id):
                return HTMLResponse(
                    f'''<div class="inline-flex items-center px-3 py-2 border border-blue-300 text-sm leading-4 font-medium rounded-md text-blue-700 bg-blue-50">
                        <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path>
                        </svg>
                        In Sonarr
                    </div>'''
                )
    except Exception as e:
        print(f"Error checking Radarr/Sonarr: {e}")
        # Fail silently and proceed with request creation

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
        is_season_request=bool(season_number)  # True if requesting specific season
    )

    session.add(new_request)
    session.commit()

    return HTMLResponse(
        f'''<div class="inline-flex items-center px-3 py-2 border border-green-300 text-sm leading-4 font-medium rounded-md text-green-700 bg-green-50">
            <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path>
            </svg>
            Requested!
        </div>'''
    )



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
        
        if current_user.is_admin:
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
                "show_request_user": current_user.is_admin or visibility_config['can_view_request_user'],
                "can_view_all_requests": current_user.is_admin or visibility_config['can_view_all_requests']
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
    
    media_request.status = RequestStatus.APPROVED
    media_request.approved_by = current_user.id
    media_request.approved_at = datetime.utcnow()
    
    session.add(media_request)
    session.commit()
    
    # Add to Radarr/Sonarr
    try:
        if media_request.media_type == MediaType.MOVIE:
            radarr_service = RadarrService(session)
            radarr_result = radarr_service.add_movie(media_request.tmdb_id)
            if radarr_result:
                media_request.radarr_id = radarr_result.get('id')
                media_request.status = RequestStatus.DOWNLOADING
        elif media_request.media_type == MediaType.TV:
            sonarr_service = SonarrService(session)
            sonarr_result = sonarr_service.add_series(media_request.tmdb_id)
            if sonarr_result:
                media_request.sonarr_id = sonarr_result.get('id')
                media_request.status = RequestStatus.DOWNLOADING
    except Exception as e:
        print(f"Error adding to Radarr/Sonarr: {e}")
        # Keep status as approved even if Radarr/Sonarr fails
    
    # Content negotiation - check if this is an HTMX request
    if request.headers.get("HX-Request"):
        # Return just the updated status badge HTML
        return HTMLResponse(f'''
        <div class="ml-2 flex-shrink-0" id="status-badge-{media_request.id}">
            <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                ✓ Approved
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
    
    media_request.status = RequestStatus.REJECTED
    media_request.approved_by = current_user.id
    media_request.approved_at = datetime.utcnow()
    
    session.add(media_request)
    session.commit()
    
    # Content negotiation - check if this is an HTMX request
    if request.headers.get("HX-Request"):
        # Return just the updated status badge HTML
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
    if not current_user.is_admin and media_request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this request")
    
    # Delete the request
    session.delete(media_request)
    session.commit()
    
    return {"message": "Request deleted successfully"}