from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from typing import Optional
from datetime import datetime

from ..core.database import get_session
from ..core.template_context import get_global_template_context
from ..models.user import User
from ..models.settings import Settings
from ..models.role import Role, PermissionFlags
from ..models.user_permissions import UserPermissions
from ..models.media_request import RequestStatus
from ..api.auth import get_current_admin_user, get_current_admin_user_flexible
from ..services.settings_service import SettingsService
from ..services.plex_service import PlexService
from ..services.plex_sync_service import PlexSyncService
from ..services.permissions_service import PermissionsService
import secrets
import string

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


def create_template_response(template_name: str, context: dict):
    """Create a template response with global context included"""
    current_user = context.get('current_user')
    global_context = get_global_template_context(current_user)
    # Merge contexts, with explicit context taking precedence
    merged_context = {**global_context, **context}
    return templates.TemplateResponse(template_name, merged_context)


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Consolidated admin dashboard with tabbed interface"""
    # Log any suspicious GET request with query parameters that might be a form redirect
    if request.query_params:
        print(f"🚨 SUSPICIOUS GET REQUEST TO /admin/ with params: {dict(request.query_params)}")
        print(f"🚨 This might be a form submission redirect!")
        print(f"🚨 Request method: {request.method}")
        print(f"🚨 Request URL: {request.url}")
        print(f"🚨 Request headers: {dict(request.headers)}")
    
    # Ensure first admin has proper role assigned
    from ..core.permissions import ensure_first_admin_has_role
    ensure_first_admin_has_role(session)
    
    # Get settings and stats for the dashboard
    settings = SettingsService.get_settings(session)
    masked_settings = settings.mask_sensitive_data()
    connection_status = settings.test_connections()
    
    # Get stats for overview
    from ..models.media_request import MediaRequest
    from ..models.plex_library_item import PlexLibraryItem
    
    total_users = len(session.exec(select(User)).all())
    pending_requests = len(session.exec(select(MediaRequest).where(MediaRequest.status == RequestStatus.PENDING)).all())
    library_items = len(session.exec(select(PlexLibraryItem)).all())
    
    stats = {
        'total_users': total_users,
        'pending_requests': pending_requests,
        'library_items': library_items
    }
    
    return create_template_response(
        "admin_dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            "settings": settings,  # Use raw settings for form fields
            "masked_settings": masked_settings,
            "connection_status": connection_status,
            "stats": stats
        }
    )


# Standalone admin settings page removed - consolidated into main dashboard
# @router.get("/settings", response_class=HTMLResponse)
# async def admin_settings(...)


@router.post("/settings/update-general")
async def update_general_settings(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session),
    
    # App settings
    app_name: str = Form("Stout Requests"),
    base_url: str = Form(""),
    require_approval: bool = Form(True),
    auto_approve_admin: bool = Form(True),
    max_requests_per_user: int = Form(10),
    site_theme: str = Form("default"),
    
    # Request visibility settings
    can_view_all_requests: bool = Form(False),
    can_view_request_user: bool = Form(False)
):
    """Update general application settings"""
    try:
        settings_data = {
            'app_name': app_name.strip(),
            'base_url': base_url.strip(),
            'require_approval': require_approval,
            'auto_approve_admin': auto_approve_admin,
            'max_requests_per_user': max_requests_per_user,
            'site_theme': site_theme.strip(),
            'can_view_all_requests': can_view_all_requests,
            'can_view_request_user': can_view_request_user
        }
        
        # Update settings (only the general ones, don't touch media settings)
        SettingsService.update_settings(session, settings_data, current_user.id)
        
        # Get current base_url for HTML responses
        current_base_url = SettingsService.get_base_url(session)
        
        # Return HTMX-friendly success message with auto-dismiss using HTMX
        from fastapi.responses import HTMLResponse
        return HTMLResponse(f"""
            <div class="p-4 bg-green-50 border border-green-200 rounded-md" 
                 hx-get="{current_base_url}/admin/clear-feedback" 
                 hx-trigger="load delay:5s" 
                 hx-swap="outerHTML">
                <div class="flex">
                    <svg class="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                    </svg>
                    <p class="ml-3 text-sm text-green-700">General settings updated successfully!</p>
                </div>
            </div>
        """)
        
    except ValueError as e:
        from fastapi.responses import HTMLResponse
        return HTMLResponse(f"""
            <div class="p-4 bg-red-50 border border-red-200 rounded-md">
                <div class="flex">
                    <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                    </svg>
                    <p class="ml-3 text-sm text-red-700">{str(e)}</p>
                </div>
            </div>
        """)
    except Exception as e:
        from fastapi.responses import HTMLResponse
        return HTMLResponse(f"""
            <div class="p-4 bg-red-50 border border-red-200 rounded-md">
                <div class="flex">
                    <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                    </svg>
                    <p class="ml-3 text-sm text-red-700">Failed to update general settings: {str(e)}</p>
                </div>
            </div>
        """)


@router.post("/settings/update-media")
async def update_media_settings(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session),
    
    # Plex settings
    plex_url: str = Form(""),
    plex_token: str = Form(""),
    plex_client_id: str = Form("stout-requests"),
    
    # TMDB settings
    tmdb_api_key: str = Form(""),
    
    # Radarr settings
    radarr_url: str = Form(""),
    radarr_api_key: str = Form(""),
    
    # Sonarr settings
    sonarr_url: str = Form(""),
    sonarr_api_key: str = Form("")
):
    """Update media application settings"""
    try:
        settings_data = {
            'plex_url': plex_url.strip() if plex_url else None,
            'plex_token': plex_token.strip() if plex_token else None,
            'plex_client_id': plex_client_id.strip(),
            'tmdb_api_key': tmdb_api_key.strip() if tmdb_api_key else None,
            'radarr_url': radarr_url.strip() if radarr_url else None,
            'radarr_api_key': radarr_api_key.strip() if radarr_api_key else None,
            'sonarr_url': sonarr_url.strip() if sonarr_url else None,
            'sonarr_api_key': sonarr_api_key.strip() if sonarr_api_key else None
        }
        
        # Update settings
        SettingsService.update_settings(session, settings_data, current_user.id)
        
        # Get current base_url for HTML responses
        current_base_url = SettingsService.get_base_url(session)
        
        # Return HTMX-friendly success message with auto-dismiss and library refresh using HTMX
        from fastapi.responses import HTMLResponse
        return HTMLResponse(f"""
            <div class="p-4 bg-green-50 border border-green-200 rounded-md" 
                 hx-get="{current_base_url}/admin/clear-feedback" 
                 hx-trigger="load delay:5s" 
                 hx-swap="outerHTML">
                <div class="flex">
                    <svg class="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                    </svg>
                    <p class="ml-3 text-sm text-green-700">Media settings updated successfully!</p>
                </div>
                <!-- Hidden element to trigger library refresh -->
                <div hx-get="{current_base_url}/admin/library/content" 
                     hx-trigger="load delay:1s" 
                     hx-target="#libraries-frame" 
                     hx-swap="innerHTML"
                     style="display: none;"></div>
            </div>
        """)
        
    except ValueError as e:
        from fastapi.responses import HTMLResponse
        return HTMLResponse(f"""
            <div class="p-4 bg-red-50 border border-red-200 rounded-md">
                <div class="flex">
                    <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                    </svg>
                    <p class="ml-3 text-sm text-red-700">{str(e)}</p>
                </div>
            </div>
        """)
    except Exception as e:
        from fastapi.responses import HTMLResponse
        return HTMLResponse(f"""
            <div class="p-4 bg-red-50 border border-red-200 rounded-md">
                <div class="flex">
                    <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                    </svg>
                    <p class="ml-3 text-sm text-red-700">Failed to update media settings: {str(e)}</p>
                </div>
            </div>
        """)


@router.post("/users/create-test")
async def create_test_user(
    username: str = Form(...),
    is_admin: bool = Form(False),
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Create a test user for testing purposes"""
    try:
        # Check if username already exists
        existing_user = session.exec(select(User).where(User.username == username)).first()
        if existing_user:
            return RedirectResponse(
                url=f"/admin?error=Username '{username}' already exists",
                status_code=303
            )
        
        # Generate a fake plex_id that won't conflict (use negative numbers for test users)
        # Find the lowest negative plex_id and decrement by 1
        lowest_test_id = session.exec(
            select(User.plex_id).where(User.plex_id < 0).order_by(User.plex_id)
        ).first()
        test_plex_id = (lowest_test_id - 1) if lowest_test_id else -1
        
        # Create test user  
        test_user = User(
            plex_id=test_plex_id,
            username=username,
            email=f"{username}@test.local",
            full_name=f"Test User - {username}",
            is_admin=is_admin,
            is_local_user=False,  # Test users are still Plex-based (with fake IDs)
            is_active=True
        )
        
        session.add(test_user)
        session.commit()
        session.refresh(test_user)
        
        return RedirectResponse(
            url=f"/admin?success=Test user '{username}' created successfully",
            status_code=303
        )
        
    except Exception as e:
        return RedirectResponse(
            url=f"/admin?error=Failed to create test user: {str(e)}",
            status_code=303
        )


@router.post("/test-login")
async def test_login(
    user_id: int = Form(...),
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Switch to test user for testing purposes (admin only)"""
    try:
        # Get the test user
        test_user = session.get(User, user_id)
        if not test_user:
            return RedirectResponse(
                url="/admin?error=Test user not found",
                status_code=303
            )
        
        # Generate a test token for this user (use username, not plex_id)
        from ..core.auth import create_access_token
        access_token = create_access_token(data={"sub": test_user.username})
        
        # Create response with redirect to logout first, then login as test user
        response = RedirectResponse(url=f"/test-user-redirect?token={access_token}&username={test_user.username}", status_code=303)
        
        # Clear all possible existing auth cookies
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("plex_token", path="/")
        response.delete_cookie("session_id", path="/")
        
        # Set the new test user token
        response.set_cookie(
            key="access_token", 
            value=access_token, 
            httponly=True, 
            path="/",
            max_age=30 * 60  # 30 minutes
        )
        
        return response
        
    except Exception as e:
        return RedirectResponse(
            url=f"/admin?error=Failed to switch to test user: {str(e)}",
            status_code=303
        )


@router.post("/settings/test-connections")
async def test_connections(
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Test connections to external services"""
    results = SettingsService.test_connections(session)
    return {"status": "success", "results": results}


@router.post("/import-friends")
async def import_friends(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Import Plex friends - supports both HTMX and API clients"""
    plex_service = PlexService(session)
    friends = plex_service.get_server_friends()
    
    # Get current base_url for HTML responses  
    current_base_url = SettingsService.get_base_url(session)
    
    imported_count = 0
    for friend_data in friends:
        # Check if user already exists
        statement = select(User).where(User.plex_id == friend_data['id'])
        existing_user = session.exec(statement).first()
        
        if not existing_user:
            user = User(
                plex_id=friend_data['id'],
                username=friend_data['username'],
                email=friend_data.get('email'),
                full_name=friend_data.get('title', friend_data['username']),
                avatar_url=friend_data.get('thumb'),
                is_local_user=False,  # Plex friends are not local users
                is_active=True
            )
            session.add(user)
            imported_count += 1
    
    session.commit()
    
    # Content negotiation: HTMX vs API clients
    if request.headers.get("HX-Request"):
        # HTMX request - return HTML with auto-dismiss
        from fastapi.responses import HTMLResponse
        return HTMLResponse(f"""
            <div class="p-4 bg-green-50 border border-green-200 rounded-md mb-4" 
                 hx-get="{current_base_url}/admin/clear-feedback" 
                 hx-trigger="load delay:5s" 
                 hx-swap="outerHTML">
                <div class="flex">
                    <svg class="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                    </svg>
                    <p class="ml-3 text-sm text-green-700">Imported {imported_count} new users successfully!</p>
                </div>
            </div>
            <div hx-get="{current_base_url}/admin/users/list" hx-target="#users-list" hx-trigger="load" style="display: none;"></div>
        """)
    else:
        # API request (mobile app, etc.) - return JSON
        return {"success": True, "message": f"Imported {imported_count} new users"}


@router.get("/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Admin users management page"""
    # Log any suspicious GET request with query parameters
    if request.query_params:
        print(f"🚨 SUSPICIOUS GET REQUEST TO /admin/users with params: {dict(request.query_params)}")
        print(f"🚨 This might be a form submission redirect!")
        print(f"🚨 Request method: {request.method}")
        print(f"🚨 Request URL: {request.url}")
        print(f"🚨 Request headers: {dict(request.headers)}")
    
    statement = select(User).order_by(User.created_at.desc())
    users = session.exec(statement).all()
    
    return templates.TemplateResponse(
        "admin_users.html",
        {"request": request, "current_user": current_user, "users": users}
    )


@router.post("/users/{user_id}/toggle-admin")
async def toggle_user_admin(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Toggle user admin status - supports both HTMX and API clients"""
    statement = select(User).where(User.id == user_id)
    user = session.exec(statement).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot modify your own admin status")
    
    # Prevent modifying server owners
    if getattr(user, 'is_server_owner', False):
        raise HTTPException(status_code=400, detail="Cannot modify server owner permissions")
    
    user.is_admin = not user.is_admin
    session.add(user)
    session.commit()
    
    # Get current base_url for HTML responses  
    current_base_url = SettingsService.get_base_url(session)
    
    # Content negotiation: HTMX vs API clients
    if request.headers.get("HX-Request"):
        # HTMX request - return HTML that triggers refresh
        from fastapi.responses import HTMLResponse
        return HTMLResponse("""
            <div hx-get="{current_base_url}/admin/users/list" hx-target="#users-list" hx-trigger="load" style="display: none;"></div>
        """)
    else:
        # API request (mobile app, etc.) - return JSON
        return {
            "success": True,
            "message": f"User '{user.username}' admin status updated to {'admin' if user.is_admin else 'user'}",
            "user": {
                "id": user.id,
                "username": user.username,
                "is_admin": user.is_admin,
                "is_active": user.is_active
            }
        }


@router.post("/users/{user_id}/toggle-active")
async def toggle_user_active(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Toggle user active status - supports both HTMX and API clients"""
    statement = select(User).where(User.id == user_id)
    user = session.exec(statement).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot modify your own active status")
    
    # Prevent modifying server owners
    if getattr(user, 'is_server_owner', False):
        raise HTTPException(status_code=400, detail="Cannot modify server owner status")
    
    user.is_active = not user.is_active
    session.add(user)
    session.commit()
    
    # Get current base_url for HTML responses  
    current_base_url = SettingsService.get_base_url(session)
    
    # Content negotiation: HTMX vs API clients
    if request.headers.get("HX-Request"):
        # HTMX request - return HTML that triggers refresh
        from fastapi.responses import HTMLResponse
        return HTMLResponse("""
            <div hx-get="{current_base_url}/admin/users/list" hx-target="#users-list" hx-trigger="load" style="display: none;"></div>
        """)
    else:
        # API request (mobile app, etc.) - return JSON
        return {
            "success": True,
            "message": f"User '{user.username}' status updated to {'active' if user.is_active else 'inactive'}",
            "user": {
                "id": user.id,
                "username": user.username,
                "is_admin": user.is_admin,
                "is_active": user.is_active
            }
        }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session),
    force: bool = False
):
    """Delete a user (admin only)"""
    statement = select(User).where(User.id == user_id)
    user = session.exec(statement).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    # Prevent deleting server owners
    if getattr(user, 'is_server_owner', False):
        raise HTTPException(status_code=400, detail="Cannot delete the server owner")
    
    # Check if user has any media requests
    from ..models.media_request import MediaRequest
    request_statement = select(MediaRequest).where(MediaRequest.user_id == user_id)
    user_requests = session.exec(request_statement).all()
    
    if user_requests and not force:
        # Prevent deletion if user has requests and force is not enabled
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot delete user with {len(user_requests)} existing requests. Use force delete to remove user and their requests."
        )
    elif user_requests and force:
        # Force delete: remove all user requests first
        print(f"🗑️ Force deleting {len(user_requests)} requests for user {user.username}")
        for request in user_requests:
            session.delete(request)
    
    # Delete the user
    session.delete(user)
    session.commit()
    
    # Get current base_url for HTML responses  
    current_base_url = SettingsService.get_base_url(session)
    
    # Return HTMX-friendly HTML response that triggers refresh
    from fastapi.responses import HTMLResponse
    return HTMLResponse(f"""
        <div hx-get="{current_base_url}/admin/users/list" hx-target="#users-list" hx-trigger="load" style="display: none;"></div>
    """)


@router.get("/users/list", response_class=HTMLResponse)
async def users_list(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get users list for HTMX"""
    from typing import List
    statement = select(User).order_by(User.created_at.desc())
    users: List[User] = session.exec(statement).all()
    
    # Get current base_url for HTML responses  
    current_base_url = SettingsService.get_base_url(session)
    
    html_content = f"""
    <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
                <tr>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">User</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Role</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Joined</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
    """
    
    # Use the new permission helper for consistent role checking
    from ..core.permissions import get_user_display_info
    
    for user in users:
        try:
            status_color = "green" if user.is_active else "red"
            status_text = "Active" if user.is_active else "Inactive"
            
            # Get role info using helper function
            user_display = get_user_display_info(user, session)
            role_text = user_display["role_text"]
            role_color = user_display["role_color"]
            is_server_owner = user_display.get("is_server_owner", False)
            
            # Format join date safely
            join_date = user.created_at.strftime('%Y-%m-%d') if user.created_at else 'Unknown'
            
            # Safe attribute access
            is_local = getattr(user, 'is_local_user', False)
            plex_id = getattr(user, 'plex_id', None)
            is_test_user = plex_id is not None and plex_id < 0
            
            # Escape HTML special characters in user data
            username = str(user.username).replace('<', '&lt;').replace('>', '&gt;')
            full_name = str(user.full_name or user.username).replace('<', '&lt;').replace('>', '&gt;')
            
            html_content += f"""
                <tr>
                    <td class="px-6 py-4 whitespace-nowrap">
                        <div class="flex items-center">
                            <div class="flex-shrink-0 h-10 w-10">
                                <div class="h-10 w-10 rounded-full bg-gray-300 flex items-center justify-center">
                                    <span class="text-sm font-medium text-gray-700">{username[0].upper()}</span>
                                </div>
                            </div>
                            <div class="ml-4">
                                <div class="text-sm font-medium text-gray-900">
                                    {full_name}
                                    {'<span class="ml-2 px-2 py-0.5 text-xs bg-purple-100 text-purple-800 rounded-full">Local User</span>' if is_local else ''}
                                    {'<span class="ml-2 px-2 py-0.5 text-xs bg-green-100 text-green-800 rounded-full">Test User</span>' if is_test_user else ''}
                                </div>
                                <div class="text-sm text-gray-500">@{username}</div>
                            </div>
                        </div>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap">
                        <span class="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-{role_color}-100 text-{role_color}-800">
                            {role_text}
                        </span>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap">
                        <span class="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-{status_color}-100 text-{status_color}-800">
                            {status_text}
                        </span>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {join_date}
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm font-medium">
                        <div class="flex space-x-2">
        """
        
            # Add test login button for test users (negative plex_id)
            if is_test_user:
                html_content += f"""
                            <form method="post" action="{current_base_url}/admin/test-login" class="inline">
                                <input type="hidden" name="user_id" value="{user.id}">
                                <button type="submit" class="text-purple-600 hover:text-purple-900 text-xs bg-purple-50 hover:bg-purple-100 px-2 py-1 rounded">
                                    Test Login
                                </button>
                            </form>
                """
            
            if user.id != current_user.id:  # Don't allow self-modification
                active_action = "Deactivate" if user.is_active else "Activate"
                active_color = "red" if user.is_active else "green"
                
                # Server owners can't be modified
                if is_server_owner:
                    html_content += f"""
                            <span class="text-xs text-gray-500 italic">Server Owner (Unchangeable)</span>"""
                else:
                    html_content += f"""
                            <button 
                                type="button"
                                class="permissions-btn text-purple-600 hover:text-purple-900 text-xs bg-purple-50 hover:bg-purple-100 px-2 py-1 rounded"
                                data-user-id="{user.id}"
                                title="Manage user permissions and role"
                                hx-disable
                                onclick="console.log('🔥 ONCLICK FIRED'); openPermissionsModal({user.id}); return false;"
                            >
                                Permissions
                            </button>
                            <button 
                                class="text-{active_color}-600 hover:text-{active_color}-900 text-xs"
                                hx-post="{current_base_url}/admin/users/{user.id}/toggle-active"
                                hx-target="#users-list"
                                hx-confirm="Are you sure you want to {active_action.lower()} this user?"
                            >
                                {active_action}
                            </button>
                            <button 
                                class="text-red-600 hover:text-red-900 text-xs"
                                hx-delete="{current_base_url}/admin/users/{user.id}"
                                hx-target="#users-list"
                                hx-confirm="⚠️ Are you sure you want to PERMANENTLY DELETE user '{user.username}'? This action cannot be undone!"
                                title="Delete user (will fail if user has requests)"
                            >
                                Delete
                            </button>
                            <button 
                                class="text-red-800 hover:text-red-900 text-xs font-bold"
                                hx-delete="{current_base_url}/admin/users/{user.id}?force=true"
                                hx-target="#users-list"
                                hx-confirm="🚨 FORCE DELETE: This will PERMANENTLY DELETE user '{user.username}' AND ALL THEIR REQUESTS! This action cannot be undone! Are you absolutely sure?"
                                title="Force delete user and all their requests"
                            >
                                Force Delete
                            </button>
                """
            else:
                html_content += """
                            <span class="text-gray-400 text-xs">Current User</span>
                """
                
            html_content += """
                        </div>
                    </td>
                </tr>
        """
        except Exception as e:
            print(f"Error processing user {getattr(user, 'username', 'unknown')}: {e}")
            # Skip this user and continue with the rest
            continue
    
    html_content += """
            </tbody>
        </table>
    </div>
    """
    
    if not users:
        html_content = """
        <div class="text-center py-8">
            <p class="text-gray-500">No users found</p>
        </div>
        """
    
    return HTMLResponse(content=html_content)


@router.get("/sync/status")
async def get_sync_status(
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get Plex library sync status"""
    sync_service = PlexSyncService(session)
    stats = sync_service.get_sync_stats()
    return stats


@router.post("/sync/trigger")
async def trigger_sync(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Manually trigger Plex library sync"""
    try:
        sync_service = PlexSyncService(session)
        result = await sync_service.sync_library()
        
        # Content negotiation
        if request.headers.get("HX-Request"):
            # HTMX web client - return HTML
            current_base_url = SettingsService.get_base_url(session)
            from fastapi.responses import HTMLResponse
            if result.get('error'):
                return HTMLResponse(f"""
                    <div class="p-4 bg-red-50 border border-red-200 rounded-md" 
                         hx-get="{current_base_url}/admin/clear-feedback" 
                     hx-trigger="load delay:5s" 
                     hx-swap="outerHTML">
                    <div class="flex">
                        <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                        </svg>
                        <p class="ml-3 text-sm text-red-700">Sync failed: {result.get('error')}</p>
                    </div>
                </div>
            """)
            else:
                # HTMX success case
                stats = result
                movies = stats.get('movies_processed', 0)
                shows = stats.get('shows_processed', 0) 
                added = stats.get('items_added', 0)
                updated = stats.get('items_updated', 0)
                
                return HTMLResponse(f"""
                    <div class="p-4 bg-green-50 border border-green-200 rounded-md" 
                         hx-get="{current_base_url}/admin/clear-feedback" 
                         hx-trigger="load delay:5s" 
                         hx-swap="outerHTML">
                        <div class="flex">
                            <svg class="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                            </svg>
                            <div class="ml-3 text-sm text-green-700">
                                <p><strong>Library sync completed!</strong></p>
                                <p>Processed {movies} movies and {shows} TV shows. Added {added}, updated {updated} items.</p>
                            </div>
                        </div>
                    </div>
                    <div hx-get="{current_base_url}/admin/library/content" hx-target="#libraries-frame" hx-trigger="load delay:1s" style="display: none;"></div>
                """)
        else:
            # API client - return JSON
            if result.get('error'):
                return {"success": False, "error": result.get('error')}
            else:
                return {"success": True, "data": result}
    except Exception as e:
        if request.headers.get("HX-Request"):
            # HTMX web client - return HTML
            current_base_url = SettingsService.get_base_url(session)
            from fastapi.responses import HTMLResponse
            return HTMLResponse(f"""
                <div class="p-4 bg-red-50 border border-red-200 rounded-md" 
                     hx-get="{current_base_url}/admin/clear-feedback" 
                     hx-trigger="load delay:5s" 
                     hx-swap="outerHTML">
                    <div class="flex">
                        <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                        </svg>
                        <p class="ml-3 text-sm text-red-700">Sync failed: {str(e)}</p>
                    </div>
                </div>
            """)
        else:
            # API client - return JSON error
            return {"success": False, "error": f"Sync failed: {str(e)}"}


@router.get("/library", response_class=HTMLResponse)
async def library_management(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Library management page with sync controls (full page)"""
    return await _get_library_content(request, current_user, session, full_page=True)


@router.get("/library/content", response_class=HTMLResponse)
async def library_management_content(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Library management content for HTMX tab loading (content only)"""
    return await _get_library_content(request, current_user, session, full_page=False)


async def _get_library_content(
    request: Request,
    current_user: User,
    session: Session,
    full_page: bool = True
):
    """Library management page with sync controls"""
    try:
        sync_service = PlexSyncService(session)
        sync_stats = sync_service.get_sync_stats()
        
        template_name = "admin_library.html" if full_page else "admin_library_content.html"
        return create_template_response(
            template_name,
            {
                "request": request,
                "current_user": current_user,
                "sync_stats": sync_stats
            }
        )
    except Exception as e:
        print(f"Error in library management: {e}")
        template_name = "admin_library.html" if full_page else "admin_library_content.html"
        return create_template_response(
            template_name,
            {
                "request": request,
                "current_user": current_user,
                "sync_stats": {"error": str(e)}
            }
        )


@router.post("/users/create-local")
async def create_local_user(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Create a new local user"""
    from ..core.password import hash_password
    
    try:
        # Get JSON data from request
        data = await request.json()
        username = data.get('username', '').strip()
        full_name = data.get('full_name', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        is_admin = data.get('is_admin', False)
        
        # Validate required fields
        if not username or not password:
            raise HTTPException(
                status_code=400,
                detail="Username and password are required"
            )
        
        # Check if username already exists
        statement = select(User).where(User.username == username)
        existing_user = session.exec(statement).first()
        
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail="Username already exists"
            )
        
        # Hash the password
        password_hash = hash_password(password)
        
        # Create the local user
        local_user = User(
            username=username,
            full_name=full_name if full_name else username,
            email=email if email else None,
            password_hash=password_hash,
            is_local_user=True,
            is_admin=is_admin,
            is_active=True
        )
        
        session.add(local_user)
        session.commit()
        
        return {
            "message": f"Local user '{username}' created successfully",
            "user": {
                "id": local_user.id,
                "username": local_user.username,
                "full_name": local_user.full_name,
                "is_admin": local_user.is_admin,
                "is_local_user": local_user.is_local_user
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating local user: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create local user"
        )


@router.get("/library/preferences")
async def get_library_preferences(
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get available libraries and current sync preferences"""
    try:
        print("🔍 Getting library preferences...")
        
        # Get available libraries from Plex
        plex_service = PlexService(session)
        print("🔄 Fetching available libraries...")
        libraries = plex_service.get_available_libraries()
        print(f"✅ Found {len(libraries)} libraries")
        
        # Get current sync preferences
        settings = SettingsService.get_settings(session)
        selected_libraries = settings.get_sync_library_preferences()
        print(f"🎯 Current preferences: {selected_libraries}")
        
        result = {
            "libraries": libraries,
            "selected_libraries": selected_libraries
        }
        print(f"📤 Returning result: {result}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error getting library preferences: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get library preferences: {str(e)}"
        )


@router.get("/clear-feedback")
async def clear_feedback():
    """Clear feedback messages (returns empty content)"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse("")


@router.get("/service-status", response_class=HTMLResponse)
async def get_service_status(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get service status for admin dashboard"""
    try:
        from ..services.radarr_service import RadarrService
        from ..services.sonarr_service import SonarrService
        
        status_items = []
        
        # Check Radarr connection
        try:
            radarr_service = RadarrService(session)
            if not radarr_service.base_url or not radarr_service.api_key:
                status_items.append({
                    "service": "Radarr",
                    "status": "not_configured",
                    "message": "Service not configured",
                    "color": "gray"
                })
            elif radarr_service.test_connection():
                status_items.append({
                    "service": "Radarr",
                    "status": "connected",
                    "message": "Connection active",
                    "color": "green"
                })
            else:
                status_items.append({
                    "service": "Radarr", 
                    "status": "disconnected",
                    "message": "Connection failed",
                    "color": "red"
                })
        except Exception as e:
            status_items.append({
                "service": "Radarr",
                "status": "error", 
                "message": f"Error: {str(e)[:50]}...",
                "color": "yellow"
            })
        
        # Check Sonarr connection
        try:
            sonarr_service = SonarrService(session)
            if not sonarr_service.base_url or not sonarr_service.api_key:
                status_items.append({
                    "service": "Sonarr",
                    "status": "not_configured",
                    "message": "Service not configured",
                    "color": "gray"
                })
            elif sonarr_service.test_connection():
                status_items.append({
                    "service": "Sonarr",
                    "status": "connected", 
                    "message": "Connection active",
                    "color": "green"
                })
            else:
                status_items.append({
                    "service": "Sonarr",
                    "status": "disconnected",
                    "message": "Connection failed", 
                    "color": "red"
                })
        except Exception as e:
            status_items.append({
                "service": "Sonarr",
                "status": "error",
                "message": f"Error: {str(e)[:50]}...",
                "color": "yellow"
            })
        
        # Generate HTML for service status notifications
        if any(item["status"] not in ["connected", "not_configured"] for item in status_items):
            # Show warnings for disconnected/error services (but not unconfigured ones)
            html_content = ""
            for item in status_items:
                if item["status"] not in ["connected", "not_configured"]:
                    icon = "⚠️" if item["status"] == "error" else "❌"
                    html_content += f'''
                    <div class="mb-2 p-3 bg-{item["color"]}-50 border border-{item["color"]}-200 rounded-md">
                        <div class="flex">
                            <span class="text-{item["color"]}-600 mr-2">{icon}</span>
                            <div class="text-sm text-{item["color"]}-700">
                                <strong>{item["service"]}:</strong> {item["message"]}
                            </div>
                        </div>
                    </div>
                    '''
            
            return HTMLResponse(html_content)
        else:
            # All services connected or not configured - return empty content
            return HTMLResponse("")
    
    except Exception as e:
        print(f"Error getting service status: {e}")
        return HTMLResponse(f'''
        <div class="mb-2 p-3 bg-red-50 border border-red-200 rounded-md">
            <div class="flex">
                <span class="text-red-600 mr-2">❌</span>
                <div class="text-sm text-red-700">
                    <strong>Service Status:</strong> Unable to check service connections
                </div>
            </div>
        </div>
        ''')




@router.post("/library/preferences")
async def update_library_preferences(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Update library sync preferences"""
    try:
        # Get JSON data from request
        data = await request.json()
        selected_libraries = data.get('selected_libraries', [])
        
        # Get current settings
        settings = SettingsService.get_settings(session)
        
        # Update sync preferences
        settings.set_sync_library_preferences(selected_libraries)
        settings.updated_at = datetime.utcnow()
        
        session.add(settings)
        session.commit()
        
        # Format message
        if selected_libraries:
            message = f"Library sync preferences updated. Will sync {len(selected_libraries)} selected libraries."
        else:
            message = "Library sync preferences cleared. Will sync all libraries."
        
        return {
            "message": message,
            "selected_libraries": selected_libraries
        }
        
    except Exception as e:
        print(f"Error updating library preferences: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to update library preferences"
        )


# ===== USER PERMISSIONS MANAGEMENT =====

@router.get("/users/{user_id}/permissions", response_class=HTMLResponse)
async def get_user_permissions_page(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get user permissions management page"""
    # Get the user
    statement = select(User).where(User.id == user_id)
    user = session.exec(statement).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get permissions service
    permissions_service = PermissionsService(session)
    
    # Get all available roles
    roles = permissions_service.get_all_roles()
    
    # Get user's current permissions
    user_permissions = permissions_service.get_user_permissions(user_id)
    user_role = permissions_service.get_user_role(user_id)
    effective_permissions = permissions_service.get_user_effective_permissions(user_id)
    
    # Get all permission flags with descriptions
    all_permissions = PermissionFlags.get_all_permissions()
    
    # Content negotiation
    if request.headers.get("HX-Request"):
        # Get base URL for the template
        base_url = SettingsService.get_base_url(session)
        return create_template_response(
            "admin_user_permissions_modal.html",
            {
                "request": request,
                "current_user": current_user,
                "target_user": user,
                "user_permissions": user_permissions,
                "user_role": user_role,
                "roles": roles,
                "effective_permissions": effective_permissions,
                "all_permissions": all_permissions,
                "base_url": base_url
            }
        )
    else:
        return {
            "user": {
                "id": user.id,
                "username": user.username,
                "is_admin": user.is_admin
            },
            "permissions": effective_permissions,
            "role": user_role.name if user_role else None,
            "available_roles": [{"id": r.id, "name": r.name, "display_name": r.display_name} for r in roles]
        }


@router.post("/users/{user_id}/permissions/role")
async def assign_user_role(
    request: Request,
    user_id: int,
    role_id: int = Form(None),
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Assign a role to a user"""
    print(f"🔍 ASSIGN ROLE: user_id={user_id}, role_id={role_id}")
    
    # Validate role_id
    if not role_id:
        raise HTTPException(status_code=400, detail="Role ID is required")
    
    # Get the user
    statement = select(User).where(User.id == user_id)
    user = session.exec(statement).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get the role
    role_statement = select(Role).where(Role.id == role_id)
    role = session.exec(role_statement).first()
    
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Assign role using permissions service
    permissions_service = PermissionsService(session)
    success = permissions_service.assign_role(user_id, role_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to assign role")
    
    # Content negotiation
    print(f"🔍 PERMISSIONS ROLE: HX-Request header: {request.headers.get('HX-Request')}")
    if request.headers.get("HX-Request"):
        print("✅ Returning HTMX modal content")
        # Reload the permissions modal content with success message
        permissions_service = PermissionsService(session)
        roles = permissions_service.get_all_roles()
        user_permissions = permissions_service.get_user_permissions(user_id)
        user_role = permissions_service.get_user_role(user_id)
        effective_permissions = permissions_service.get_user_effective_permissions(user_id)
        all_permissions = PermissionFlags.get_all_permissions()
        
        base_url = SettingsService.get_base_url(session)
        context = {
            "request": request,
            "current_user": current_user,
            "target_user": user,
            "user_permissions": user_permissions,
            "user_role": user_role,
            "roles": roles,
            "effective_permissions": effective_permissions,
            "all_permissions": all_permissions,
            "base_url": base_url,
            "success_message": f'Role "{role.display_name}" assigned to {user.username}'
        }
        return create_template_response("admin_user_permissions_modal.html", context)
    else:
        return {
            "success": True,
            "message": f"Role '{role.display_name}' assigned to {user.username}",
            "user_id": user_id,
            "role": {"id": role.id, "name": role.name, "display_name": role.display_name}
        }


@router.post("/users/{user_id}/permissions/custom")
async def set_user_custom_permission(
    request: Request,
    user_id: int,
    permission: str = Form(...),
    enabled: bool = Form(...),
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Set a custom permission for a user"""
    # Get the user
    statement = select(User).where(User.id == user_id)
    user = session.exec(statement).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Validate permission
    all_permissions = PermissionFlags.get_all_permissions()
    if permission not in all_permissions:
        raise HTTPException(status_code=400, detail="Invalid permission")
    
    # Set permission using permissions service
    permissions_service = PermissionsService(session)
    success = permissions_service.set_user_permission(user_id, permission, enabled)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set permission")
    
    action = "granted" if enabled else "revoked"
    
    # Content negotiation
    if request.headers.get("HX-Request"):
        # Reload the permissions modal content with success message
        permissions_service = PermissionsService(session)
        roles = permissions_service.get_all_roles()
        user_permissions = permissions_service.get_user_permissions(user_id)
        user_role = permissions_service.get_user_role(user_id)
        effective_permissions = permissions_service.get_user_effective_permissions(user_id)
        all_permissions = PermissionFlags.get_all_permissions()
        
        base_url = SettingsService.get_base_url(session)
        context = {
            "request": request,
            "current_user": current_user,
            "target_user": user,
            "user_permissions": user_permissions,
            "user_role": user_role,
            "roles": roles,
            "effective_permissions": effective_permissions,
            "all_permissions": all_permissions,
            "base_url": base_url,
            "success_message": f'Permission "{all_permissions[permission]}" {action} for {user.username}'
        }
        return create_template_response("admin_user_permissions_modal.html", context)
    else:
        return {
            "success": True,
            "message": f"Permission '{permission}' {action} for {user.username}",
            "user_id": user_id,
            "permission": permission,
            "enabled": enabled
        }


@router.post("/users/{user_id}/permissions/save")
async def save_user_permissions(
    request: Request,
    user_id: int,
    role_id: Optional[int] = Form(None),
    max_requests: Optional[int] = Form(None),
    request_retention_days: Optional[int] = Form(None),
    auto_approve: bool = Form(False),
    can_request_movies: Optional[bool] = Form(None),
    can_request_tv: Optional[bool] = Form(None),
    can_request_4k: Optional[bool] = Form(None),
    movie_quality_profile_id: Optional[int] = Form(None),
    tv_quality_profile_id: Optional[int] = Form(None),
    notification_enabled: bool = Form(False),
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Save all user permissions in one go"""
    try:
        print(f"🔍 SAVE PERMISSIONS ENDPOINT HIT!")
        print(f"🔍 Request method: {request.method}")
        print(f"🔍 Request URL: {request.url}")
        print(f"🔍 Request headers: {dict(request.headers)}")
        print(f"🔍 HX-Request header: {request.headers.get('HX-Request')}")
        print(f"🔍 Content-Type: {request.headers.get('Content-Type')}")
        print(f"🔍 Form data - user_id={user_id}, role_id={role_id}, max_requests={max_requests}")
        
        # Get the user
        statement = select(User).where(User.id == user_id)
        user = session.exec(statement).first()
        
        if not user:
            if request.headers.get("HX-Request"):
                return HTMLResponse('<div class="p-4 bg-red-50 border border-red-200 rounded-md"><p class="text-red-800">User not found</p></div>')
            return {"success": False, "message": "User not found"}
        
        # Initialize permissions service
        permissions_service = PermissionsService(session)
        
        # Assign role if provided
        if role_id:
            success = permissions_service.assign_role(user_id, role_id)
            if not success:
                if request.headers.get("HX-Request"):
                    return HTMLResponse('<div class="p-4 bg-red-50 border border-red-200 rounded-md"><p class="text-red-800">Failed to assign role</p></div>')
                return {"success": False, "message": "Failed to assign role"}
        
        # Get or create user permissions
        user_permissions = permissions_service.get_user_permissions(user_id)
        if not user_permissions:
            from ..models.user_permissions import UserPermissions
            user_permissions = UserPermissions(user_id=user_id)
            session.add(user_permissions)
        
        # Update permissions based on form data
        if max_requests is not None:
            user_permissions.max_requests = max_requests
        if request_retention_days is not None:
            user_permissions.request_retention_days = request_retention_days
        user_permissions.auto_approve_enabled = auto_approve
        if can_request_movies is not None:
            user_permissions.can_request_movies = can_request_movies
        if can_request_tv is not None:
            user_permissions.can_request_tv = can_request_tv
        if can_request_4k is not None:
            user_permissions.can_request_4k = can_request_4k
        if movie_quality_profile_id is not None:
            user_permissions.movie_quality_profile_id = movie_quality_profile_id
        if tv_quality_profile_id is not None:
            user_permissions.tv_quality_profile_id = tv_quality_profile_id
        user_permissions.notification_enabled = notification_enabled
        user_permissions.updated_at = datetime.utcnow()
        
        # Save changes
        session.add(user_permissions)
        session.commit()
        
        # Content negotiation for HTMX vs API
        if request.headers.get("HX-Request"):
            # For HTMX, return empty response - let the JavaScript handle UI updates
            from fastapi.responses import HTMLResponse
            return HTMLResponse("")
        else:
            return {
                "success": True, 
                "message": f"Permissions updated for {user.username}"
            }
        
    except Exception as e:
        print(f"❌ Error saving permissions: {e}")
        session.rollback()
        if request.headers.get("HX-Request"):
            return HTMLResponse(f'<div class="p-4 bg-red-50 border border-red-200 rounded-md"><p class="text-red-800">Error: {str(e)}</p></div>')
        return {"success": False, "message": f"Error saving permissions: {str(e)}"}


@router.post("/users/{user_id}/permissions/limits")
async def set_user_limits(
    request: Request,
    user_id: int,
    max_requests: Optional[int] = Form(None),
    request_retention_days: Optional[int] = Form(None),
    auto_approve: bool = Form(False),
    can_request_movies: Optional[bool] = Form(None),
    can_request_tv: Optional[bool] = Form(None),
    can_request_4k: Optional[bool] = Form(None),
    movie_quality_profile_id: Optional[int] = Form(None),
    tv_quality_profile_id: Optional[int] = Form(None),
    notification_enabled: bool = Form(False),
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Set user-specific limits and media permissions"""
    # Get the user
    statement = select(User).where(User.id == user_id)
    user = session.exec(statement).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get or create user permissions
    permissions_service = PermissionsService(session)
    user_perms = permissions_service.get_user_permissions(user_id)
    
    if user_perms:
        # Update existing permissions
        if max_requests is not None:
            user_perms.max_requests = max_requests
        if request_retention_days is not None:
            user_perms.request_retention_days = request_retention_days
        user_perms.auto_approve_enabled = auto_approve
        if can_request_movies is not None:
            user_perms.can_request_movies = can_request_movies
        if can_request_tv is not None:
            user_perms.can_request_tv = can_request_tv
        if can_request_4k is not None:
            user_perms.can_request_4k = can_request_4k
        if movie_quality_profile_id is not None:
            user_perms.movie_quality_profile_id = movie_quality_profile_id
        if tv_quality_profile_id is not None:
            user_perms.tv_quality_profile_id = tv_quality_profile_id
        user_perms.notification_enabled = notification_enabled
        user_perms.updated_at = datetime.utcnow()
        
        session.add(user_perms)
        session.commit()
    
    # Content negotiation
    if request.headers.get("HX-Request"):
        # Reload the permissions modal content with success message
        permissions_service = PermissionsService(session)
        roles = permissions_service.get_all_roles()
        user_permissions = permissions_service.get_user_permissions(user_id)
        user_role = permissions_service.get_user_role(user_id)
        effective_permissions = permissions_service.get_user_effective_permissions(user_id)
        all_permissions = PermissionFlags.get_all_permissions()
        
        base_url = SettingsService.get_base_url(session)
        context = {
            "request": request,
            "current_user": current_user,
            "target_user": user,
            "user_permissions": user_permissions,
            "user_role": user_role,
            "roles": roles,
            "effective_permissions": effective_permissions,
            "all_permissions": all_permissions,
            "base_url": base_url,
            "success_message": f'User limits updated for {user.username}'
        }
        return create_template_response("admin_user_permissions_modal.html", context)
    else:
        return {
            "success": True,
            "message": f"User limits updated for {user.username}",
            "user_id": user_id,
            "limits": {
                "max_requests": max_requests,
                "auto_approve": auto_approve,
                "can_request_movies": can_request_movies,
                "can_request_tv": can_request_tv,
                "can_request_4k": can_request_4k
            }
        }


@router.get("/roles", response_class=HTMLResponse)
async def get_roles_management(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get roles management page"""
    permissions_service = PermissionsService(session)
    roles = permissions_service.get_all_roles()
    all_permissions = PermissionFlags.get_all_permissions()
    
    # Content negotiation
    if request.headers.get("HX-Request"):
        return create_template_response(
            "admin_roles_management.html",
            {
                "request": request,
                "current_user": current_user,
                "roles": roles,
                "all_permissions": all_permissions
            }
        )
    else:
        return {
            "roles": [
                {
                    "id": r.id,
                    "name": r.name,
                    "display_name": r.display_name,
                    "description": r.description,
                    "permissions": r.get_permissions(),
                    "is_system": r.is_system,
                    "is_default": r.is_default
                } for r in roles
            ],
            "available_permissions": all_permissions
        }


@router.get("/jobs/content", response_class=HTMLResponse)
async def admin_jobs_content(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get scheduled jobs content for admin dashboard"""
    try:
        from ..services.background_jobs import background_jobs
        
        # Get job status information
        jobs_info = {
            "download_status_check": {
                "name": "Download Status Check",
                "description": "Checks Radarr/Sonarr for download status updates",
                "interval": "2 minutes",
                "running": background_jobs.running,
                "last_run": background_jobs.last_download_check.strftime("%Y-%m-%d %H:%M:%S UTC") if background_jobs.last_download_check else "Never",
                "next_run": None  # Will be calculated
            }
        }
        
        # Calculate next run time
        if background_jobs.last_download_check:
            from datetime import timedelta
            next_run = background_jobs.last_download_check + timedelta(seconds=background_jobs.download_status_interval)
            jobs_info["download_status_check"]["next_run"] = next_run.strftime("%Y-%m-%d %H:%M:%S UTC")
        
        return create_template_response("admin_jobs.html", {
            "request": request,
            "current_user": current_user,
            "jobs": jobs_info
        })
        
    except Exception as e:
        print(f"Error loading jobs content: {e}")
        return HTMLResponse(f'<div class="text-red-600">Error loading jobs: {str(e)}</div>')


@router.post("/jobs/trigger-download-status")
async def trigger_download_status_job(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Manually trigger download status check job"""
    try:
        from ..services.background_jobs import trigger_download_status_check
        
        stats = await trigger_download_status_check()
        
        # Content negotiation
        if request.headers.get("HX-Request"):
            # HTMX web client - return HTML
            base_url = SettingsService.get_base_url(session)
            
            if stats.get('errors', 0) > 0:
                return HTMLResponse(f"""
                    <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-md" 
                         hx-get="{base_url}/admin/clear-feedback"
                         hx-trigger="load delay:5s">
                        <div class="flex">
                            <svg class="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                            </svg>
                            <div class="ml-3 text-sm text-yellow-700">
                                <p><strong>Download status check completed with errors!</strong></p>
                                <p>Checked {stats.get('checked', 0)} requests. Updated {stats.get('updated_to_downloading', 0)} to downloading, {stats.get('updated_to_downloaded', 0)} to downloaded. {stats.get('errors', 0)} errors occurred.</p>
                            </div>
                        </div>
                    </div>
                """)
            else:
                checked = stats.get('checked', 0)
                downloading = stats.get('updated_to_downloading', 0)
                downloaded = stats.get('updated_to_downloaded', 0)
                
                return HTMLResponse(f"""
                    <div class="p-4 bg-green-50 border border-green-200 rounded-md" 
                         hx-get="{base_url}/admin/clear-feedback"
                         hx-trigger="load delay:5s">
                        <div class="flex">
                            <svg class="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                            </svg>
                            <div class="ml-3 text-sm text-green-700">
                                <p><strong>Download status check completed!</strong></p>
                                <p>Checked {checked} requests. Updated {downloading} to downloading, {downloaded} to downloaded.</p>
                            </div>
                        </div>
                    </div>
                """)
        else:
            # API client - return JSON
            return {
                "success": True,
                "message": "Download status check triggered successfully",
                "stats": stats
            }
            
    except Exception as e:
        print(f"Error triggering download status check: {e}")
        if request.headers.get("HX-Request"):
            base_url = SettingsService.get_base_url(session)
            return HTMLResponse(f"""
                <div class="p-4 bg-red-50 border border-red-200 rounded-md" 
                     hx-get="{base_url}/admin/clear-feedback"
                     hx-trigger="load delay:5s">
                    <div class="flex">
                        <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                        </svg>
                        <div class="ml-3 text-sm text-red-700">
                            <p><strong>Error triggering download status check!</strong></p>
                            <p>{str(e)}</p>
                        </div>
                    </div>
                </div>
            """)
        else:
            return {
                "success": False,
                "message": f"Error triggering download status check: {str(e)}"
            }

