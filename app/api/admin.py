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
from ..api.auth import get_current_admin_user, get_current_admin_user_flexible
from ..services.settings_service import SettingsService
from ..services.plex_service import PlexService
from ..services.plex_sync_service import PlexSyncService
import secrets
import string

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


def create_template_response(template_name: str, context: dict):
    """Create a template response with global context included"""
    global_context = get_global_template_context()
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
    # Get settings and stats for the dashboard
    settings = SettingsService.get_settings(session)
    masked_settings = settings.mask_sensitive_data()
    connection_status = settings.test_connections()
    
    # Get stats for overview
    from ..models.media_request import MediaRequest
    from ..models.plex_library_item import PlexLibraryItem
    
    total_users = len(session.exec(select(User)).all())
    pending_requests = len(session.exec(select(MediaRequest).where(MediaRequest.status == 'pending')).all())
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
    
    for user in users:
        try:
            status_color = "green" if user.is_active else "red"
            status_text = "Active" if user.is_active else "Inactive"
            role_color = "yellow" if user.is_admin else "blue"
            role_text = "Admin" if user.is_admin else "User"
            
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
                admin_action = "Remove Admin" if user.is_admin else "Make Admin"
                admin_color = "red" if user.is_admin else "blue"
                
                active_action = "Deactivate" if user.is_active else "Activate"
                active_color = "red" if user.is_active else "green"
                
                html_content += f"""
                            <button 
                                class="text-{admin_color}-600 hover:text-{admin_color}-900 text-xs"
                                hx-post="{current_base_url}/admin/users/{user.id}/toggle-admin"
                                hx-target="#users-list"
                                hx-confirm="Are you sure you want to {admin_action.lower()} this user?"
                            >
                                {admin_action}
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
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Manually trigger Plex library sync"""
    try:
        sync_service = PlexSyncService(session)
        result = await sync_service.sync_library()
        
        # Get current base_url for HTML responses  
        current_base_url = SettingsService.get_base_url(session)
        
        # Return HTMX-friendly HTML response
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
    except Exception as e:
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