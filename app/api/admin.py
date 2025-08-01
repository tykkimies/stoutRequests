from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlmodel import Session, select
from typing import Optional
from datetime import datetime
from pydantic import BaseModel

from ..core.database import get_session
from ..core.template_context import get_global_template_context
from ..models.user import User
from ..models.settings import Settings
from ..models.role import Role, PermissionFlags
from ..models.user_permissions import UserPermissions
from ..models.media_request import RequestStatus
from ..api.auth import get_current_admin_user, get_current_admin_user_flexible, get_current_user_flexible
from ..core.permission_decorators import require_permission, require_any_permission
from ..services.settings_service import SettingsService
from ..services.plex_service import PlexService
from ..services.plex_sync_service import PlexSyncService
from ..services.permissions_service import PermissionsService
import secrets
import string
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


def create_template_response(template_name: str, context: dict):
    """Create a template response with global context included"""
    current_user = context.get('current_user')
    request = context.get('request')
    global_context = get_global_template_context(current_user, request)
    # Merge contexts, with explicit context taking precedence
    merged_context = {**global_context, **context}
    print(f"🔧 [ADMIN API] Template: {template_name}")
    print(f"🔧 [ADMIN API] Global context base_url: '{global_context.get('base_url', 'MISSING')}'")
    print(f"🔧 [ADMIN API] Final merged context base_url: '{merged_context.get('base_url', 'MISSING')}'")
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
@require_permission(PermissionFlags.ADMIN_MANAGE_SETTINGS)
async def update_general_settings(
    request: Request,
    current_user: User = Depends(get_current_user_flexible),
    session: Session = Depends(get_session),
    
    # App settings (truly global)
    app_name: str = Form("Stout Requests"),
    base_url: str = Form(""),
    max_requests_per_user: int = Form(10),
    site_theme: str = Form("default")
):
    """Update general application settings (global settings only)"""
    try:
        settings_data = {
            'app_name': app_name.strip(),
            'base_url': base_url.strip(),
            'max_requests_per_user': max_requests_per_user,
            'site_theme': site_theme.strip()
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
@require_permission(PermissionFlags.ADMIN_MANAGE_SETTINGS)
async def update_media_settings(
    request: Request,
    current_user: User = Depends(get_current_user_flexible),
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
                url=build_app_url(f"/admin?error=Username '{username}' already exists"),
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
            url=build_app_url(f"/admin?success=Test user '{username}' created successfully"),
            status_code=303
        )
        
    except Exception as e:
        return RedirectResponse(
            url=build_app_url(f"/admin?error=Failed to create test user: {str(e)}"),
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
                url=build_app_url("/admin?error=Test user not found"),
                status_code=303
            )
        
        # Generate a test token for this user (use username, not plex_id)
        from ..core.auth import create_access_token
        access_token = create_access_token(data={"sub": test_user.username})
        
        # Create response with redirect to logout first, then login as test user
        response = RedirectResponse(url=build_app_url(f"/test-user-redirect?token={access_token}&username={test_user.username}"), status_code=303)
        
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
            url=build_app_url(f"/admin?error=Failed to switch to test user: {str(e)}"),
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
        # Check if user already exists by plex_id OR username (due to unique constraints)
        plex_id_statement = select(User).where(User.plex_id == friend_data['id'])
        username_statement = select(User).where(User.username == friend_data['username'])
        
        existing_by_plex_id = session.exec(plex_id_statement).first()
        existing_by_username = session.exec(username_statement).first()
        
        if not existing_by_plex_id and not existing_by_username:
            # User doesn't exist, create new one
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
        elif existing_by_username and not existing_by_plex_id:
            # Username exists but different plex_id - update the plex_id
            print(f"🔄 Updating plex_id for existing user: {friend_data['username']}")
            existing_by_username.plex_id = friend_data['id']
            session.add(existing_by_username)
        else:
            print(f"ℹ️  User already exists: {friend_data['username']}")
    
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
@require_permission(PermissionFlags.ADMIN_MANAGE_USERS)
async def toggle_user_admin(
    request: Request,
    user_id: int,
    current_user: User = Depends(get_current_user_flexible),
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
        # HTMX request - reload the users list
        return await users_list(request, current_user, session)
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
    request: Request,
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
    
    # Check and clean up user permissions
    from ..models.user_permissions import UserPermissions
    permissions_statement = select(UserPermissions).where(UserPermissions.user_id == user_id)
    user_permissions = session.exec(permissions_statement).all()
    
    if user_permissions:
        print(f"🗑️ Cleaning up {len(user_permissions)} permission records for user {user.username}")
        for permission in user_permissions:
            session.delete(permission)
    
    # Check and clean up any other related records (category preferences, etc.)
    try:
        from ..models.user_category_preferences import UserCategoryPreferences
        category_prefs_statement = select(UserCategoryPreferences).where(UserCategoryPreferences.user_id == user_id)
        category_prefs = session.exec(category_prefs_statement).all()
        
        if category_prefs:
            print(f"🗑️ Cleaning up {len(category_prefs)} category preference records for user {user.username}")
            for pref in category_prefs:
                session.delete(pref)
    except ImportError:
        print(f"⚠️ UserCategoryPreferences model not found, skipping category cleanup")
    except Exception as e:
        print(f"⚠️ Could not clean up category preferences: {e}")
    
    # Delete the user
    session.delete(user)
    session.commit()
    
    # Get current base_url for HTML responses  
    current_base_url = SettingsService.get_base_url(session)
    
    # Return updated users list for HTMX
    return await users_list(request, current_user, session)


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
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Instance Access</th>
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
            try:
                user_display = get_user_display_info(user, session)
                role_text = user_display["role_text"]
                role_color = user_display["role_color"] 
                is_server_owner = user_display.get("is_server_owner", False)
            except Exception as role_error:
                print(f"❌ Error getting display info for user {user.username} (ID: {user.id}): {role_error}")
                # Fallback values
                role_text = "Unknown"
                role_color = "gray"
                is_server_owner = False
            
            # Format join date safely
            join_date = user.created_at.strftime('%Y-%m-%d') if user.created_at else 'Unknown'
            
            # Safe attribute access
            is_local = getattr(user, 'is_local_user', False)
            plex_id = getattr(user, 'plex_id', None)
            is_test_user = plex_id is not None and plex_id < 0
            
            # Escape HTML special characters in user data
            username = str(user.username or '').replace('<', '&lt;').replace('>', '&gt;')
            full_name = str(user.full_name or user.username or 'Unknown User').replace('<', '&lt;').replace('>', '&gt;')
            
            # Safe username initial - handle empty usernames
            username_initial = username[0].upper() if username else '?'
            
            html_content += f"""
                <tr>
                    <td class="px-6 py-4 whitespace-nowrap">
                        <div class="flex items-center">
                            <div class="flex-shrink-0 h-10 w-10">
                                <div class="h-10 w-10 rounded-full bg-gray-300 flex items-center justify-center">
                                    <span class="text-sm font-medium text-gray-700">{username_initial}</span>
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
                        <!-- Instance access info - managed via main permissions modal -->
                        <span class="text-xs text-gray-600">Via Permissions</span>
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
            print(f"❌ Error processing user {getattr(user, 'username', 'unknown')} (ID: {getattr(user, 'id', 'unknown')}): {e}")
            import traceback
            print(f"❌ Full traceback: {traceback.format_exc()}")
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


@router.get("/debug/sync-preferences")
async def debug_sync_preferences(
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Debug endpoint to check current sync preferences"""
    try:
        settings = SettingsService.get_settings(session)
        selected_libraries = settings.get_sync_library_preferences()
        
        # Also get available libraries for comparison
        plex_service = PlexService(session)
        available_libraries = plex_service.get_available_libraries()
        
        return {
            "selected_libraries": selected_libraries,
            "available_libraries": [{"title": lib["title"], "type": lib["type"]} for lib in available_libraries],
            "raw_sync_library_preferences": settings.sync_library_preferences,
            "should_sync_results": {lib["title"]: settings.should_sync_library(lib["title"]) for lib in available_libraries}
        }
    except Exception as e:
        return {"error": str(e)}


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
            elif await radarr_service.test_connection():
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
            elif await sonarr_service.test_connection():
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
    
    print(f"🔍 LOADING PERMISSIONS MODAL for user_id: {user_id}")
    print(f"🔍 User permissions found: {user_permissions is not None}")
    if user_permissions:
        print(f"🔍 Role ID: {user_permissions.role_id}")
        print(f"🔍 Auto-approve: {user_permissions.auto_approve_enabled}")
        print(f"🔍 Movies: {user_permissions.can_request_movies}")
        print(f"🔍 TV: {user_permissions.can_request_tv}")
        print(f"🔍 4K: {user_permissions.can_request_4k}")
        print(f"🔍 Updated at: {user_permissions.updated_at}")
        
        # Debug custom permissions specifically
        custom_perms = user_permissions.get_custom_permissions()
        print(f"🔍 Custom permissions JSON: {user_permissions.custom_permissions}")
        print(f"🔍 Custom permissions dict: {custom_perms}")
        print(f"🔍 Can view other users requests: {custom_perms.get('can_view_other_users_requests')}")
        print(f"🔍 Can see requester username: {custom_perms.get('can_see_requester_username')}")
    else:
        print("🔍 No user permissions found - will create defaults")
    
    print(f"🔍 User role: {user_role.display_name if user_role else 'None'}")
    print(f"🔍 Effective permissions object: {type(effective_permissions)}")
    print(f"🔍 Effective permissions: {effective_permissions}")
    
    # Test specific effective permissions for the checkboxes
    can_movies_effective = permissions_service.can_request_media_type(user_id, 'movie')
    can_tv_effective = permissions_service.can_request_media_type(user_id, 'tv')
    can_4k_effective = permissions_service.can_request_4k(user_id)
    print(f"🔍 Effective - Movies: {can_movies_effective}, TV: {can_tv_effective}, 4K: {can_4k_effective}")
    
    # Create a custom effective permissions object for the template
    template_effective_permissions = {
        'can_request_movies': can_movies_effective,
        'can_request_tv': can_tv_effective,
        'can_request_4k': can_4k_effective,
        'auto_approve_enabled': user_permissions.auto_approve_enabled if user_permissions else False
    }
    print(f"🔍 Template effective permissions: {template_effective_permissions}")
    
    # Get all permission flags with descriptions
    all_permissions = PermissionFlags.get_all_permissions()
    
    # Get all available service instances for instance permissions
    from ..models.service_instance import ServiceInstance
    available_service_instances = session.exec(
        select(ServiceInstance).where(ServiceInstance.is_enabled == True)
    ).all()
    
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
                "template_effective_permissions": template_effective_permissions,
                "all_permissions": all_permissions,
                "available_service_instances": available_service_instances,
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


class UserPermissionsUpdate(BaseModel):
    """Request model for updating user permissions"""
    role_id: Optional[int] = None
    max_requests: Optional[int] = None
    auto_approve: bool = False
    can_request_movies: Optional[bool] = None  # None = inherit from role
    can_request_tv: Optional[bool] = None
    can_view_other_users_requests: Optional[bool] = None
    can_see_requester_username: Optional[bool] = None


@router.post("/users/{user_id}/permissions/save")
async def save_user_permissions(
    request: Request,
    user_id: int,
    permissions_data: UserPermissionsUpdate,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Save all user permissions in one go (accepts JSON)"""
    try:
        print(f"🔍 SAVE PERMISSIONS ENDPOINT HIT for user_id: {user_id}")
        print(f"🔍 Request method: {request.method}")
        print(f"🔍 Content-Type: {request.headers.get('Content-Type')}")
        print(f"🔍 Permissions data: {permissions_data}")
        print(f"🔍 Role ID to assign: {permissions_data.role_id}")
        print(f"🔍 Auto-approve: {permissions_data.auto_approve}")
        print(f"🔍 Can request movies: {permissions_data.can_request_movies} (None=inherit, True=allow, False=deny)")
        print(f"🔍 Can request TV: {permissions_data.can_request_tv} (None=inherit, True=allow, False=deny)")
        print(f"🔍 Custom permissions - view others: {permissions_data.can_view_other_users_requests}")
        print(f"🔍 Custom permissions - see usernames: {permissions_data.can_see_requester_username}")
        
        # Get the user
        statement = select(User).where(User.id == user_id)
        user = session.exec(statement).first()
        
        if not user:
            return {"success": False, "message": "User not found"}
        
        # Get existing user permissions (don't auto-create to avoid transaction conflicts)
        from ..models.user_permissions import UserPermissions
        statement = select(UserPermissions).where(UserPermissions.user_id == user_id)
        user_permissions = session.exec(statement).first()
        
        # Get permissions service and user role for override calculations
        permissions_service = PermissionsService(session)
        user_role = permissions_service.get_user_role(user_id)
        
        print(f"🔍 Found existing permissions: {user_permissions is not None}")
        if user_permissions:
            print(f"🔍 Current values BEFORE update:")
            print(f"🔍   Role ID: {user_permissions.role_id}")
            print(f"🔍   Movies: {user_permissions.can_request_movies}")
            print(f"🔍   TV: {user_permissions.can_request_tv}")
            print(f"🔍   4K: {user_permissions.can_request_4k}")
            print(f"🔍   Auto-approve: {user_permissions.auto_approve_enabled}")
        
        # Create new permissions if none exist
        if not user_permissions:
            print(f"🔍 Creating new UserPermissions record for user_id: {user_id}")
            user_permissions = UserPermissions(user_id=user_id)
        else:
            print(f"🔍 Updating existing UserPermissions record for user_id: {user_id}")
        
        # Assign role if provided
        if permissions_data.role_id:
            user_permissions.role_id = permissions_data.role_id
        
        # Update permissions based on JSON data
        if permissions_data.max_requests is not None:
            user_permissions.max_requests = permissions_data.max_requests
        user_permissions.auto_approve_enabled = permissions_data.auto_approve
        
        # Calculate permission overrides based on desired effective permissions vs role permissions
        role_permissions = user_role.get_permissions() if user_role else {}
        from ..models.role import PermissionFlags
        
        # For each permission, determine if we need an override
        def calculate_override(desired_effective: bool, role_permission_key: str):
            role_allows = role_permissions.get(role_permission_key, False)
            if desired_effective == role_allows:
                # Desired matches role - no override needed
                return None
            else:
                # Desired differs from role - need explicit override
                return desired_effective
        
        user_permissions.can_request_movies = calculate_override(
            permissions_data.can_request_movies, PermissionFlags.REQUEST_MOVIES
        )
        user_permissions.can_request_tv = calculate_override(
            permissions_data.can_request_tv, PermissionFlags.REQUEST_TV
        )
        
        print(f"🔍 Calculated overrides:")
        print(f"🔍   Movies: desired={permissions_data.can_request_movies}, role={role_permissions.get(PermissionFlags.REQUEST_MOVIES, False)}, override={user_permissions.can_request_movies}")
        print(f"🔍   TV: desired={permissions_data.can_request_tv}, role={role_permissions.get(PermissionFlags.REQUEST_TV, False)}, override={user_permissions.can_request_tv}")
        
        # Handle new permission fields via custom_permissions JSON
        custom_perms = user_permissions.get_custom_permissions()
        print(f"🔍 BEFORE updating custom permissions: {custom_perms}")
        custom_perms['can_view_other_users_requests'] = permissions_data.can_view_other_users_requests
        custom_perms['can_see_requester_username'] = permissions_data.can_see_requester_username
        print(f"🔍 AFTER updating custom permissions: {custom_perms}")
        user_permissions.set_custom_permissions(custom_perms)
        print(f"🔍 Custom permissions JSON string set to: {user_permissions.custom_permissions}")
        
        user_permissions.updated_at = datetime.utcnow()
        
        print(f"🔍 Values being saved:")
        print(f"🔍   Role ID: {user_permissions.role_id}")
        print(f"🔍   Movies: {user_permissions.can_request_movies}")
        print(f"🔍   TV: {user_permissions.can_request_tv}")
        print(f"🔍   4K: {user_permissions.can_request_4k}")
        print(f"🔍   Auto-approve: {user_permissions.auto_approve_enabled}")
        print(f"🔍   Updated at: {user_permissions.updated_at}")
        
        print(f"🔍 About to save with merge() and commit()...")
        
        # Save changes - use merge for existing records to handle primary key properly
        try:
            saved_permissions = session.merge(user_permissions)  # Use merge instead of add for existing records
            print(f"🔍 Merge completed successfully")
            
            session.commit()
            print(f"🔍 Commit completed successfully")
            
            print(f"✅ Successfully saved permissions for user {user.username}")
            print(f"✅ Final values - Role ID: {saved_permissions.role_id}, Auto-approve: {saved_permissions.auto_approve_enabled}")
            print(f"✅ Movies: {saved_permissions.can_request_movies}, TV: {saved_permissions.can_request_tv}, 4K: {saved_permissions.can_request_4k}")
        except Exception as save_error:
            print(f"❌ ERROR during save: {save_error}")
            session.rollback()
            raise save_error
        
        # Verify the data was actually saved by re-querying
        verification_statement = select(UserPermissions).where(UserPermissions.user_id == user_id)
        verification_perms = session.exec(verification_statement).first()
        if verification_perms:
            print(f"✅ VERIFICATION - Data persisted in database:")
            print(f"✅ VERIFICATION - Role ID: {verification_perms.role_id}")
            print(f"✅ VERIFICATION - Auto-approve: {verification_perms.auto_approve_enabled}")
            print(f"✅ VERIFICATION - Movies: {verification_perms.can_request_movies}")
            print(f"✅ VERIFICATION - TV: {verification_perms.can_request_tv}")
            print(f"✅ VERIFICATION - 4K: {verification_perms.can_request_4k}")
            print(f"✅ VERIFICATION - Updated at: {verification_perms.updated_at}")
            
            # Verify custom permissions
            verification_custom_perms = verification_perms.get_custom_permissions()
            print(f"✅ VERIFICATION - Custom permissions JSON: {verification_perms.custom_permissions}")
            print(f"✅ VERIFICATION - Custom permissions dict: {verification_custom_perms}")
            print(f"✅ VERIFICATION - Can view other users requests: {verification_custom_perms.get('can_view_other_users_requests')}")
            print(f"✅ VERIFICATION - Can see requester username: {verification_custom_perms.get('can_see_requester_username')}")
        else:
            print("❌ VERIFICATION FAILED - No permissions found after save!")
        
        return {
            "success": True, 
            "message": f"Permissions updated for {user.username}"
        }
        
    except Exception as e:
        print(f"❌ Error saving permissions: {e}")
        session.rollback()
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
        if movie_quality_profile_id is not None:
            user_perms.movie_quality_profile_id = movie_quality_profile_id
        if tv_quality_profile_id is not None:
            user_perms.tv_quality_profile_id = tv_quality_profile_id
        user_perms.notification_enabled = notification_enabled
        user_perms.updated_at = datetime.utcnow()
        
        # Process instance permissions from form data
        form_data = await request.form()
        instance_permissions = {}
        
        # Category permissions
        instance_permissions['category_4k'] = 'category_4k' in form_data
        instance_permissions['category_anime'] = 'category_anime' in form_data
        instance_permissions['category_foreign'] = 'category_foreign' in form_data
        
        # Instance-specific permissions - check all instances explicitly
        from app.models.service_instance import ServiceInstance
        all_instances = session.exec(select(ServiceInstance)).all()
        for instance in all_instances:
            instance_key = f'instance_{instance.id}'
            instance_permissions[instance_key] = instance_key in form_data
        
        # Update instance permissions
        user_perms.set_instance_permissions(instance_permissions)
        
        # Handle custom permissions
        custom_perms = user_perms.get_custom_permissions()
        custom_perms['can_view_other_users_requests'] = 'can_view_other_users_requests' in form_data
        custom_perms['can_see_requester_username'] = 'can_see_requester_username' in form_data
        user_perms.set_custom_permissions(custom_perms)
        
        print(f"🔍 [LIMITS ENDPOINT] Updated custom permissions for user {user_id}: {custom_perms}")
        
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
        
        # Get service instances for the modal
        from ..models.service_instance import ServiceInstance
        available_service_instances = session.exec(
            select(ServiceInstance).where(ServiceInstance.is_enabled == True)
        ).all()
        
        # Create template effective permissions for checkboxes
        template_effective_permissions = {
            'can_request_movies': permissions_service.can_request_media_type(user_id, 'movie'),
            'can_request_tv': permissions_service.can_request_media_type(user_id, 'tv'),
            'can_request_4k': permissions_service.can_request_4k(user_id),
            'auto_approve_enabled': user_permissions.auto_approve_enabled if user_permissions else False
        }
        
        base_url = SettingsService.get_base_url(session)
        context = {
            "request": request,
            "current_user": current_user,
            "target_user": user,
            "user_permissions": user_permissions,
            "user_role": user_role,
            "roles": roles,
            "effective_permissions": effective_permissions,
            "template_effective_permissions": template_effective_permissions,
            "all_permissions": all_permissions,
            "available_service_instances": available_service_instances,
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
                "can_request_tv": can_request_tv
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



@router.get("/jobs/status")
async def admin_jobs_status(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get job status data for auto-refresh (JSON only)"""
    try:
        from ..services.background_jobs import background_jobs
        from ..services.plex_sync_service import PlexSyncService

        # Get job status
        all_jobs = background_jobs.get_all_jobs_status()
        
        # Get library sync stats
        sync_stats = None
        try:
            sync_service = PlexSyncService(session)
            sync_stats = sync_service.get_sync_stats()
        except Exception as e:
            print(f"Error getting sync stats: {e}")
            sync_stats = {'error': str(e)}
        
        # Format the jobs for JSON response
        jobs_info = {}
        for job_name, job_data in all_jobs.items():
            jobs_info[job_name] = {
                'name': job_data.get('name', job_name.replace('_', ' ').title()),
                'description': job_data.get('description', ''),
                'interval': f"Every {job_data.get('interval_seconds', 3600) // 60} minutes",
                'last_run': job_data.get('last_run').strftime('%Y-%m-%d %H:%M:%S') if job_data.get('last_run') else 'Never',
                'next_run': job_data.get('next_run').strftime('%Y-%m-%d %H:%M:%S') if job_data.get('next_run') else 'Not scheduled',
                'running': job_data.get('running', False),
                'stats': job_data.get('stats', {})
            }
        
        return {
            "success": True,
            "jobs": jobs_info,
            "sync_stats": sync_stats
        }
        
    except Exception as e:
        print(f"Error getting jobs status: {e}")
        return {
            "success": False,
            "error": str(e),
            "jobs": {},
            "sync_stats": {}
        }


@router.post("/jobs/trigger-library-sync")
async def trigger_library_sync_job(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Manually trigger library sync job"""
    try:
        from ..services.background_jobs import trigger_library_sync
        
        result = await trigger_library_sync()
        
        # Content negotiation
        if request.headers.get("HX-Request"):
            # HTMX web client - return HTML
            base_url = SettingsService.get_base_url(session)
            
            if result.get('success'):
                stats = result.get('stats', {})
                movies = stats.get('movies_processed', 0)
                shows = stats.get('shows_processed', 0) 
                added = stats.get('items_added', 0)
                updated = stats.get('items_updated', 0)
                
                return HTMLResponse(f"""
                    <div class="p-4 bg-green-50 border border-green-200 rounded-md" 
                         hx-get="{base_url}/admin/clear-feedback"
                         hx-trigger="load delay:5s">
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
                    <div hx-get="{base_url}/admin/jobs/content" hx-target="#jobs-frame" hx-trigger="load delay:3s" style="display: none;"></div>
                """)
            else:
                return HTMLResponse(f"""
                    <div class="p-4 bg-red-50 border border-red-200 rounded-md" 
                         hx-get="{base_url}/admin/clear-feedback"
                         hx-trigger="load delay:5s">
                        <div class="flex">
                            <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                            </svg>
                            <div class="ml-3 text-sm text-red-700">
                                <p><strong>Library sync failed!</strong></p>
                                <p>{result.get('message', 'Unknown error')}</p>
                            </div>
                        </div>
                    </div>
                """)
        else:
            # API client - return JSON
            return result
            
    except Exception as e:
        print(f"Error triggering library sync: {e}")
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
                            <p><strong>Error triggering library sync!</strong></p>
                            <p>{str(e)}</p>
                        </div>
                    </div>
                </div>
            """)
        else:
            return {
                "success": False,
                "message": f"Error triggering library sync: {str(e)}"
            }


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


# HTMX Tab Content Endpoints
@router.get("/tabs/overview", response_class=HTMLResponse)
async def admin_overview_tab(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get overview tab content"""
    try:
        # Get stats
        from sqlmodel import select, func
        from ..models.user import User
        from ..models.media_request import MediaRequest, RequestStatus
        
        total_users = session.exec(select(func.count(User.id))).first()
        pending_requests = session.exec(
            select(func.count(MediaRequest.id)).where(MediaRequest.status == RequestStatus.PENDING)
        ).first()
        
        # Get connection status
        connection_status = {"all_connected": True}  # Simplified for now
        
        stats = {
            "total_users": total_users or 0,
            "pending_requests": pending_requests or 0,
            "library_items": 0  # TODO: Get from Plex
        }
        
        return create_template_response("admin_tabs/overview.html", {
            "request": request,
            "current_user": current_user,
            "stats": stats,
            "connection_status": connection_status
        })
        
    except Exception as e:
        return HTMLResponse(f'<div class="text-red-600">Error loading overview: {str(e)}</div>')


@router.get("/tabs/users", response_class=HTMLResponse)
async def admin_users_tab(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get users tab content"""
    return create_template_response("admin_tabs/users.html", {
        "request": request,
        "current_user": current_user
    })


@router.get("/tabs/general", response_class=HTMLResponse)
async def admin_general_tab(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get general settings tab content"""
    settings = SettingsService.get_settings(session)
    return create_template_response("admin_tabs/general.html", {
        "request": request,
        "current_user": current_user,
        "settings": settings
    })


@router.get("/tabs/media-servers", response_class=HTMLResponse)
async def admin_media_servers_tab(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get media servers tab content"""
    settings = SettingsService.get_settings(session)
    return create_template_response("admin_tabs/media_servers.html", {
        "request": request,
        "current_user": current_user,
        "settings": settings
    })


@router.post("/settings/update-media-servers", response_class=HTMLResponse)
async def update_media_servers_settings(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Update media server settings"""
    try:
        form_data = await request.form()
        
        # Handle library preferences
        monitored_libraries = form_data.getlist("monitored_libraries")
        import json
        library_preferences_json = json.dumps(monitored_libraries) if monitored_libraries else None
        
        # Create settings data dictionary for update
        settings_data = {
            "plex_url": form_data.get("plex_url", "").strip(),
            "plex_token": form_data.get("plex_token", "").strip(),
            "sync_library_preferences": library_preferences_json
        }
        
        # Save to database using the correct format
        SettingsService.update_settings(session, settings_data, current_user.id)
        
        if request.headers.get("HX-Request"):
            # Get current base_url for HTML responses
            current_base_url = SettingsService.get_base_url(session)
            return HTMLResponse(
                '<div class="p-3 bg-green-50 border border-green-200 rounded-md">'
                '<p class="text-green-800 font-medium">✓ Media server settings updated successfully</p>'
                '</div>'
                f'<div hx-get="{current_base_url}/admin/clear-feedback" hx-trigger="load delay:3s" hx-target="#settings-feedback"></div>'
            )
        else:
            return {"success": True, "message": "Media server settings updated successfully"}
            
    except Exception as e:
        logger.error(f"Error updating media server settings: {e}")
        if request.headers.get("HX-Request"):
            return HTMLResponse(
                '<div class="p-3 bg-red-50 border border-red-200 rounded-md">'
                f'<p class="text-red-800 font-medium">✗ Error updating settings: {str(e)}</p>'
                '</div>'
                '<div hx-get="/admin/clear-feedback" hx-trigger="load delay:5s" hx-target="#settings-feedback"></div>'
            )
        else:
            return {"success": False, "error": str(e)}


@router.post("/test-connection", response_class=HTMLResponse)
async def test_plex_connection(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Test Plex server connection"""
    try:
        form_data = await request.form()
        plex_url = form_data.get("plex_url", "").strip()
        plex_token = form_data.get("plex_token", "").strip()
        
        if not plex_url or not plex_token:
            return HTMLResponse(
                '<div class="flex items-center text-red-600">'
                '<svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">'
                '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>'
                '</svg>'
                '<span class="text-sm">URL and token are required</span>'
                '</div>'
            )
        
        # Create a temporary settings object to test connection
        temp_settings = Settings()
        temp_settings.plex_url = plex_url
        temp_settings.plex_token = plex_token
        
        # Use the existing test_connections method
        results = temp_settings.test_connections()
        plex_result = results.get('plex', {})
        
        if plex_result.get('status') == 'connected':
            return HTMLResponse(
                '<div class="flex items-center text-green-600">'
                '<svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">'
                '<path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path>'
                '</svg>'
                f'<span class="text-sm">{plex_result.get("message", "Connection successful")}</span>'
                '</div>'
            )
        else:
            return HTMLResponse(
                '<div class="flex items-center text-red-600">'
                '<svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">'
                '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>'
                '</svg>'
                f'<span class="text-sm">{plex_result.get("message", "Connection failed")}</span>'
                '</div>'
            )
        
    except Exception as e:
        logger.error(f"Error testing Plex connection: {e}")
        return HTMLResponse(
            '<div class="flex items-center text-red-600">'
            '<svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">'
            '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>'
            '</svg>'
            f'<span class="text-sm">Connection error: {str(e)}</span>'
            '</div>'
        )


@router.post("/load-libraries", response_class=HTMLResponse)
async def load_plex_libraries(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Load available Plex libraries"""
    try:
        form_data = await request.form()
        plex_url = form_data.get("plex_url", "").strip()
        plex_token = form_data.get("plex_token", "").strip()
        
        if not plex_url or not plex_token:
            return HTMLResponse(
                '<div class="text-sm text-red-600">URL and token are required to load libraries</div>'
            )
        
        # Create a temporary settings object with the provided credentials
        temp_settings = Settings()
        temp_settings.plex_url = plex_url
        temp_settings.plex_token = plex_token
        
        # Use the existing Plex service to get libraries
        plex_service = PlexService(session=session)
        plex_service.plex_url = plex_url
        plex_service.plex_token = plex_token
        
        try:
            # Try to get libraries using the Plex service
            libraries = plex_service.get_available_libraries()
            
            if not libraries:
                return HTMLResponse(
                    '<div class="text-sm text-gray-600">No libraries found or connection failed</div>'
                )
            
            # Get current library preferences
            settings = SettingsService.get_settings(session)
            current_preferences = settings.get_sync_library_preferences()
            
            html = '<div class="grid grid-cols-2 gap-3">'
            found_media_libs = False
            
            for lib in libraries:
                lib_type = lib.get("type", "unknown")
                lib_name = lib.get("title", "Unknown")
                lib_key = str(lib.get("key", ""))
                
                # Only show movie and show libraries
                if lib_type in ["movie", "show"]:
                    found_media_libs = True
                    checked = 'checked' if lib_name in current_preferences else ''
                    html += f'''
                    <div class="flex items-center p-2 bg-white border border-gray-200 rounded text-sm">
                        <input type="checkbox" name="monitored_libraries" value="{lib_name}" 
                               id="lib_{lib_key}" {checked} class="h-4 w-4 text-orange-600 border-gray-300 rounded flex-shrink-0">
                        <label for="lib_{lib_key}" class="ml-2 flex-1 min-w-0">
                            <span class="font-medium text-gray-900 truncate block">{lib_name}</span>
                            <span class="text-xs text-gray-500">({lib_type})</span>
                        </label>
                    </div>
                    '''
            
            html += '</div>'
            
            if not found_media_libs:
                html = '<div class="text-sm text-gray-600">No movie or TV show libraries found</div>'
            
            return HTMLResponse(html)
            
        except Exception as plex_error:
            # Fallback to direct requests approach
            import requests
            headers = {"X-Plex-Token": plex_token}
            response = requests.get(f"{plex_url}/library/sections", headers=headers, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                libraries = data.get("MediaContainer", {}).get("Directory", [])
                
                # Get current library preferences
                settings = SettingsService.get_settings(session)
                current_preferences = settings.get_sync_library_preferences()
                
                html = '<div class="grid grid-cols-2 gap-3">'
                found_media_libs = False
                
                for lib in libraries:
                    lib_type = lib.get("type", "unknown")
                    lib_name = lib.get("title", "Unknown")
                    lib_key = str(lib.get("key", ""))
                    
                    # Only show movie and show libraries
                    if lib_type in ["movie", "show"]:
                        found_media_libs = True
                        checked = 'checked' if lib_name in current_preferences else ''
                        html += f'''
                        <div class="flex items-center p-2 bg-white border border-gray-200 rounded text-sm">
                            <input type="checkbox" name="monitored_libraries" value="{lib_name}" 
                                   id="lib_{lib_key}" {checked} class="h-4 w-4 text-orange-600 border-gray-300 rounded flex-shrink-0">
                            <label for="lib_{lib_key}" class="ml-2 flex-1 min-w-0">
                                <span class="font-medium text-gray-900 truncate block">{lib_name}</span>
                                <span class="text-xs text-gray-500">({lib_type})</span>
                            </label>
                        </div>
                        '''
                
                html += '</div>'
                
                if not found_media_libs:
                    html = '<div class="text-sm text-gray-600">No movie or TV show libraries found</div>'
                
                return HTMLResponse(html)
            else:
                return HTMLResponse(
                    f'<div class="text-sm text-red-600">Failed to load libraries (HTTP {response.status_code})</div>'
                )
        
    except Exception as e:
        logger.error(f"Error loading Plex libraries: {e}")
        return HTMLResponse(
            f'<div class="text-sm text-red-600">Error loading libraries: {str(e)}</div>'
        )




@router.get("/clear-feedback", response_class=HTMLResponse)
async def clear_feedback(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible)
):
    """Clear feedback messages"""
    return HTMLResponse("")


@router.get("/tabs/services", response_class=HTMLResponse)
async def admin_services_tab(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get services tab content"""
    settings = SettingsService.get_settings(session)
    return create_template_response("admin_tabs/services.html", {
        "request": request,
        "current_user": current_user,
        "settings": settings
    })


# Radarr Service Endpoints
@router.get("/services/radarr/list", response_class=HTMLResponse)
async def list_radarr_instances(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """List all Radarr instances"""
    from sqlmodel import select
    from ..models.service_instance import ServiceInstance, ServiceType
    
    # Get all Radarr instances from database
    statement = select(ServiceInstance).where(ServiceInstance.service_type == ServiceType.RADARR)
    instances = session.exec(statement).all()
    
    if not instances:
        return HTMLResponse('''
            <div class="p-6 text-center text-gray-500">
                <svg class="w-12 h-12 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
                </svg>
                <p class="text-sm">No Radarr instances configured</p>
                <p class="text-xs text-gray-400 mt-1">Add an instance to get started with movie automation</p>
            </div>
        ''')
    
    # Get current base_url for HTML responses  
    current_base_url = SettingsService.get_base_url(session)
    
    # Build HTML for each instance
    instances_html = ""
    for instance in instances:
        # Test connection automatically to get current status
        try:
            current_result = await instance.test_connection()
            # Save the updated test result
            session.add(instance)
            session.commit()
            test_result = current_result
        except Exception as e:
            print(f"Error testing Radarr {instance.name}: {e}")
            test_result = instance.get_test_result()
        
        status_color = "green" if test_result.get("status") == "connected" else "red"
        status_text = "Connected" if test_result.get("status") == "connected" else "Disconnected"
        
        # Get settings for display
        settings = instance.get_settings()
        hostname = settings.get("hostname", "Unknown")
        port = settings.get("port", "Unknown")
        use_ssl = settings.get("use_ssl", False)
        protocol = "HTTPS" if use_ssl else "HTTP"
        enable_integration = settings.get('enable_integration', True)
        
        instances_html += f'''
            <div class="p-4 border-b border-gray-200 last:border-b-0">
                <div class="flex items-center justify-between">
                    <div class="flex-1">
                        <div class="flex items-center">
                            <h4 class="text-lg font-medium text-gray-900">{instance.name}</h4>
                            <span class="ml-3 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-{status_color}-100 text-{status_color}-800">
                                <div class="w-2 h-2 bg-{status_color}-400 rounded-full mr-1"></div>
                                {status_text}
                            </span>
                        </div>
                        <div class="mt-1 text-sm text-gray-500">
                            <span>{protocol}://{hostname}:{port}</span>
                            {f' • Version: {test_result.get("version", "Unknown")}' if test_result.get("version") else ''}
                        </div>
                        <div class="mt-1 text-xs text-gray-400">
                            Created: {instance.created_at.strftime("%Y-%m-%d %H:%M") if instance.created_at else "Unknown"}
                            {f' • Last tested: {instance.last_tested_at.strftime("%Y-%m-%d %H:%M")}' if instance.last_tested_at else ''}
                        </div>
                        <div class="mt-2 flex items-center">
                            <span class="text-xs text-gray-600 mr-2">Integration:</span>
                            <button type="button"
                                    onclick="toggleServiceIntegration({instance.id}, 'radarr', this)"
                                    data-enabled="{'true' if enable_integration else 'false'}"
                                    class="relative inline-flex h-4 w-7 items-center rounded-full transition-colors focus:outline-none focus:ring-1 focus:ring-blue-500 focus:ring-offset-1 {'bg-blue-600' if enable_integration else 'bg-gray-300'}">
                                <span class="inline-block h-3 w-3 transform rounded-full bg-white transition-transform {'translate-x-3.5' if enable_integration else 'translate-x-0.5'}"></span>
                            </button>
                        </div>
                    </div>
                    <div class="flex items-center space-x-2">
                        <button type="button" 
                                hx-post="{current_base_url}/admin/services/radarr/{instance.id}/test"
                                hx-target="#instance-{instance.id}-status"
                                class="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-xs font-medium">
                            Test
                        </button>
                        <button type="button" 
                                hx-get="{current_base_url}/admin/services/radarr/{instance.id}/edit"
                                hx-target="#service-modal-content"
                                onclick="showServiceModal('Edit Radarr Instance')"
                                class="bg-gray-600 hover:bg-gray-700 text-white px-3 py-1 rounded text-xs font-medium">
                            Edit
                        </button>
                        <button type="button" 
                                hx-delete="{current_base_url}/admin/services/radarr/{instance.id}"
                                hx-target="#radarr-instances"
                                hx-confirm="Are you sure you want to delete this Radarr instance?"
                                class="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded text-xs font-medium">
                            Delete
                        </button>
                    </div>
                </div>
                <div id="instance-{instance.id}-status" class="mt-2"></div>
            </div>
        '''
    
    return HTMLResponse(instances_html)


@router.get("/services/radarr/{instance_id}/edit", response_class=HTMLResponse)
async def edit_radarr_form(
    instance_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get Radarr instance edit form with existing data"""
    try:
        from sqlmodel import select
        from ..models.service_instance import ServiceInstance, ServiceType
        
        # Get the instance
        statement = select(ServiceInstance).where(
            ServiceInstance.id == instance_id,
            ServiceInstance.service_type == ServiceType.RADARR
        )
        instance = session.exec(statement).first()
        
        if not instance:
            return HTMLResponse('''
                <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-800 text-sm">✗ Radarr instance not found</p>
                </div>
            ''')
        
        # Get current base_url for HTML responses  
        current_base_url = SettingsService.get_base_url(session)
        
        # Get instance settings
        settings = instance.get_settings()
        hostname = settings.get("hostname", "")
        port = settings.get("port", 7878)
        use_ssl = settings.get("use_ssl", False)
        base_url = settings.get("base_url", "")
        quality_profile_id = settings.get("quality_profile_id", "")
        root_folder_path = settings.get("root_folder_path", "")
        minimum_availability = settings.get("minimum_availability", "inCinemas")
        monitored = settings.get("monitored", True)
        search_for_movie = settings.get("search_for_movie", True)
        enable_scan = settings.get("enable_scan", True)
        enable_automatic_search = settings.get("enable_automatic_search", True)
        enable_integration = settings.get("enable_integration", True)
        tags = settings.get("tags", [])
        
        # Try to fetch current quality profiles and root folders from Radarr
        quality_profiles_html = '<option value="">Select quality profile...</option>'
        root_folders_html = '<option value="">Select root folder...</option>'
        
        try:
            from ..services.radarr_service import RadarrService
            radarr_service = RadarrService(session)
            
            # Set the service to use this specific instance
            radarr_service.instance = instance
            radarr_service.base_url = instance.url
            radarr_service.api_key = instance.api_key
            radarr_service.headers = {
                'X-Api-Key': instance.api_key,
                'Content-Type': 'application/json'
            } if instance.api_key else {}
            
            # Fetch quality profiles
            profiles = await radarr_service.get_quality_profiles()
            for profile in profiles:
                selected = 'selected' if str(profile.get('id')) == str(quality_profile_id) else ''
                quality_profiles_html += f'<option value="{profile.get("id")}" {selected}>{profile.get("name", "Unknown")}</option>'
            
            # Fetch root folders  
            folders = await radarr_service.get_root_folders()
            for folder in folders:
                selected = 'selected' if folder.get('path') == root_folder_path else ''
                root_folders_html += f'<option value="{folder.get("path")}" {selected}>{folder.get("path")}</option>'
                
        except Exception as e:
            print(f"Could not fetch Radarr data for edit form: {e}")
            # Fallback to showing saved values if service is unreachable
            if quality_profile_id:
                quality_profiles_html += f'<option value="{quality_profile_id}" selected>Profile ID {quality_profile_id} (Saved)</option>'
            if root_folder_path:
                root_folders_html += f'<option value="{root_folder_path}" selected>{root_folder_path} (Saved)</option>'
        
        return HTMLResponse(f'''
            <div>
                <h4 class="text-lg font-medium text-gray-900 mb-6">Edit Radarr Instance</h4>
                <form hx-post="{current_base_url}/admin/services/radarr/{instance_id}/update" hx-target="#radarr-instances" class="space-y-6">
                    
                    <!-- Instance Name -->
                    <div>
                        <label for="radarr_name" class="block text-sm font-medium text-gray-700 mb-2">Instance Name</label>
                        <input type="text" name="radarr_name" id="radarr_name" 
                               value="{instance.name}"
                               placeholder="e.g., Radarr 4K, Movies HD"
                               class="block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                    </div>
                    
                    <!-- Connection Settings -->
                    <div>
                        <h5 class="text-md font-semibold text-gray-900 mb-4">Connection Settings</h5>
                        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div>
                                <label for="radarr_hostname" class="block text-sm font-medium text-gray-700">Hostname/IP</label>
                                <input type="text" name="radarr_hostname" id="radarr_hostname" 
                                       value="{hostname}"
                                       placeholder="172.20.0.11 or localhost"
                                       class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                            </div>
                            
                            <div>
                                <label for="radarr_port" class="block text-sm font-medium text-gray-700">Port</label>
                                <input type="number" name="radarr_port" id="radarr_port" 
                                       value="{port}"
                                       min="1" max="65535"
                                       class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                            </div>
                            
                            <div class="flex items-end">
                                <div class="flex items-center h-10">
                                    <input type="checkbox" name="use_ssl" id="use_ssl" 
                                           {"checked" if use_ssl else ""}
                                           class="h-4 w-4 text-orange-600 border-gray-300 rounded">
                                    <label for="use_ssl" class="ml-2 text-sm text-gray-700">Use HTTPS</label>
                                </div>
                            </div>
                        </div>
                        
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                            <div>
                                <label for="radarr_api_key" class="block text-sm font-medium text-gray-700">API Key</label>
                                <input type="password" name="radarr_api_key" id="radarr_api_key" 
                                       value="{instance.api_key}"
                                       placeholder="Your Radarr API key"
                                       class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                            </div>
                            
                            <div>
                                <label for="radarr_base_url" class="block text-sm font-medium text-gray-700">Base URL</label>
                                <input type="text" name="radarr_base_url" id="radarr_base_url" 
                                       value="{base_url}"
                                       placeholder="/radarr (optional)"
                                       class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                            </div>
                        </div>
                    </div>
                    
                    <!-- Test Connection -->
                    <div>
                        <button type="button" 
                                hx-post="{current_base_url}/admin/services/radarr/test" 
                                hx-target="#test-results"
                                hx-include="form"
                                class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-md text-sm font-medium">
                            <svg class="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                            </svg>
                            Test Connection
                        </button>
                        <div id="test-results" class="mt-4"></div>
                    </div>
                    
                    <!-- Advanced Settings -->
                    <div class="border-t pt-4">
                        <button type="button" onclick="toggleAdvancedSettings()" 
                                class="flex items-center justify-between w-full text-left focus:outline-none">
                            <h5 class="text-md font-semibold text-gray-900">Advanced Settings</h5>
                            <svg id="advanced-chevron" class="w-5 h-5 text-gray-500 transform transition-transform duration-200" 
                                 fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                            </svg>
                        </button>
                        
                        <div id="radarr-advanced-settings" class="mt-4 space-y-4">
                            <!-- Default Settings -->
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div>
                                    <label for="radarr_quality_profile_id" class="block text-sm font-medium text-gray-700">Quality Profile</label>
                                    <select name="radarr_quality_profile_id" id="radarr_quality_profile_id" 
                                            class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                                        {quality_profiles_html}
                                    </select>
                                </div>
                                
                                <div>
                                    <label for="radarr_root_folder_path" class="block text-sm font-medium text-gray-700">Root Folder</label>
                                    <select name="radarr_root_folder_path" id="radarr_root_folder_path" 
                                            class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                                        {root_folders_html}
                                    </select>
                                </div>
                                
                                <div>
                                    <label for="minimum_availability" class="block text-sm font-medium text-gray-700">Minimum Availability</label>
                                    <select name="minimum_availability" id="minimum_availability" 
                                            class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                                        <option value="announced" {"selected" if minimum_availability == "announced" else ""}>Announced</option>
                                        <option value="inCinemas" {"selected" if minimum_availability == "inCinemas" else ""}>In Cinemas</option>
                                        <option value="released" {"selected" if minimum_availability == "released" else ""}>Released</option>
                                        <option value="preDB" {"selected" if minimum_availability == "preDB" else ""}>PreDB</option>
                                    </select>
                                </div>
                                
                                <div>
                                    <label for="tags" class="block text-sm font-medium text-gray-700">Tags</label>
                                    <input type="text" name="tags" id="tags" 
                                           value="{', '.join(tags) if isinstance(tags, list) else tags}"
                                           placeholder="4k, uhd, remux (comma separated)"
                                           class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                                    <p class="mt-1 text-xs text-gray-500">Optional tags to apply to requests</p>
                                </div>
                            </div>
                            
                            <!-- Multi-Instance Configuration -->
                            <div class="border-t pt-4 mt-4">
                                <h6 class="text-sm font-semibold text-gray-900 mb-3">Multi-Instance Configuration</h6>
                                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div>
                                        <label for="instance_category" class="block text-sm font-medium text-gray-700 mb-2">Instance Category</label>
                                        <select name="instance_category" id="instance_category" 
                                                class="block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                                            <option value="">Standard</option>
                                            <option value="4k" {"selected" if instance.instance_category == "4k" else ""}>4K</option>
                                            <option value="anime" {"selected" if instance.instance_category == "anime" else ""}>Anime</option>
                                            <option value="foreign" {"selected" if instance.instance_category == "foreign" else ""}>Foreign</option>
                                            <option value="family" {"selected" if instance.instance_category == "family" else ""}>Family</option>
                                        </select>
                                        <p class="mt-1 text-xs text-gray-500">Categorize this instance for specialized content</p>
                                    </div>
                                    
                                    <div>
                                        <label for="quality_tier" class="block text-sm font-medium text-gray-700 mb-2">Quality Tier</label>
                                        <select name="quality_tier" id="quality_tier" 
                                                class="block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                                            <option value="standard" {"selected" if (instance.quality_tier or "standard") == "standard" else ""}>Standard</option>
                                            <option value="4k" {"selected" if instance.quality_tier == "4k" else ""}>4K</option>
                                            <option value="hdr" {"selected" if instance.quality_tier == "hdr" else ""}>HDR</option>
                                        </select>
                                        <p class="mt-1 text-xs text-gray-500">Quality tier this instance handles</p>
                                    </div>
                                </div>
                                
                                <div class="mt-4 space-y-2">
                                    <div class="flex items-center">
                                        <input type="checkbox" name="is_default_movie" id="is_default_movie" 
                                               {"checked" if instance.is_default_movie else ""}
                                               class="h-4 w-4 text-orange-600 border-gray-300 rounded">
                                        <label for="is_default_movie" class="ml-2 text-sm text-gray-700">
                                            Default instance for movie requests
                                        </label>
                                    </div>
                                    
                                    <div class="flex items-center">
                                        <input type="checkbox" name="is_4k_default" id="is_4k_default" 
                                               {"checked" if instance.is_4k_default else ""}
                                               class="h-4 w-4 text-orange-600 border-gray-300 rounded">
                                        <label for="is_4k_default" class="ml-2 text-sm text-gray-700">
                                            Default instance for 4K movie requests
                                        </label>
                                    </div>
                                </div>
                            </div>
                            
                            <!-- Automation Options -->
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4">
                                <div class="flex items-center">
                                    <input type="checkbox" name="enable_scan" id="enable_scan" 
                                           {"checked" if enable_scan else ""}
                                           class="h-4 w-4 text-orange-600 border-gray-300 rounded">
                                    <label for="enable_scan" class="ml-2 text-sm text-gray-700">
                                        Enable library scanning
                                    </label>
                                </div>
                                
                                <div class="flex items-center">
                                    <input type="checkbox" name="enable_automatic_search" id="enable_automatic_search" 
                                           {"checked" if enable_automatic_search else ""}
                                           class="h-4 w-4 text-orange-600 border-gray-300 rounded">
                                    <label for="enable_automatic_search" class="ml-2 text-sm text-gray-700">
                                        Enable automatic search on approval
                                    </label>
                                </div>
                                
                                <div class="flex items-center mt-3">
                                    <input type="checkbox" name="enable_integration" id="enable_integration" 
                                           {"checked" if enable_integration else ""}
                                           class="h-4 w-4 text-orange-600 border-gray-300 rounded">
                                    <label for="enable_integration" class="ml-2 text-sm text-gray-700">
                                        Enable automatic integration (send approved requests to Radarr)
                                    </label>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Form Actions -->
                    <div class="flex justify-end space-x-3 pt-6 border-t">
                        <button type="button" onclick="hideServiceModal()"
                                class="bg-gray-300 hover:bg-gray-400 text-gray-700 px-4 py-2 rounded-md text-sm font-medium">
                            Cancel
                        </button>
                        <button type="submit" 
                                class="bg-orange-600 hover:bg-orange-700 text-white px-4 py-2 rounded-md text-sm font-medium">
                            Update Instance
                        </button>
                    </div>
                </form>
            </div>
        ''')
        
    except Exception as e:
        logger.error(f"Error loading Radarr edit form: {e}")
        return HTMLResponse(f'''
            <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                <p class="text-red-800 text-sm">✗ Error loading edit form: {str(e)}</p>
            </div>
        ''')


@router.post("/services/radarr/{instance_id}/update", response_class=HTMLResponse)
async def update_radarr_instance(
    instance_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Update an existing Radarr instance"""
    try:
        from sqlmodel import select
        from ..models.service_instance import ServiceInstance, ServiceType
        
        # Get the instance
        statement = select(ServiceInstance).where(
            ServiceInstance.id == instance_id,
            ServiceInstance.service_type == ServiceType.RADARR
        )
        instance = session.exec(statement).first()
        
        if not instance:
            return HTMLResponse('''
                <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-800 text-sm">✗ Radarr instance not found</p>
                </div>
            ''')
        
        # Extract form data
        form_data = await request.form()
        radarr_name = form_data.get("radarr_name", "").strip()
        radarr_hostname = form_data.get("radarr_hostname", "").strip()
        radarr_port = form_data.get("radarr_port", "7878").strip()
        radarr_api_key = form_data.get("radarr_api_key", "").strip()
        use_ssl = form_data.get("use_ssl") == "on"
        radarr_base_url = form_data.get("radarr_base_url", "").strip()
        
        # Validation
        if not radarr_name or not radarr_hostname or not radarr_port or not radarr_api_key:
            return HTMLResponse('''
                <div class="p-3 bg-red-50 border border-red-200 rounded-md mb-4">
                    <p class="text-red-800 text-sm">✗ Instance name, hostname, port, and API key are required</p>
                </div>
            ''')
        
        # Build URL from components
        protocol = "https" if use_ssl else "http"
        radarr_url = f"{protocol}://{radarr_hostname}:{radarr_port}"
        
        # Extract multi-instance configuration
        instance_category = form_data.get("instance_category", "").strip() or None
        quality_tier = form_data.get("quality_tier", "standard").strip()
        is_default_movie = form_data.get("is_default_movie") == "on"
        is_4k_default = form_data.get("is_4k_default") == "on"
        
        # Update instance
        instance.name = radarr_name
        instance.url = radarr_url
        instance.api_key = radarr_api_key
        instance.instance_category = instance_category
        instance.quality_tier = quality_tier
        instance.is_default_movie = is_default_movie
        instance.is_4k_default = is_4k_default
        
        # Handle default instance conflicts
        if is_default_movie:
            # Clear other default movie instances
            other_defaults = session.exec(select(ServiceInstance).where(
                ServiceInstance.service_type == ServiceType.RADARR,
                ServiceInstance.id != instance_id,
                ServiceInstance.is_default_movie == True
            )).all()
            for other_instance in other_defaults:
                other_instance.is_default_movie = False
                session.add(other_instance)
        
        if is_4k_default:
            # Clear other 4K default instances
            other_4k_defaults = session.exec(select(ServiceInstance).where(
                ServiceInstance.service_type == ServiceType.RADARR,
                ServiceInstance.id != instance_id,
                ServiceInstance.is_4k_default == True
            )).all()
            for other_instance in other_4k_defaults:
                other_instance.is_4k_default = False
                session.add(other_instance)
        
        # Update settings - extract all form data with correct field names
        quality_profile_id = form_data.get("radarr_quality_profile_id", "").strip()
        root_folder_path = form_data.get("radarr_root_folder_path", "").strip()
        minimum_availability = form_data.get("minimum_availability", "inCinemas").strip()
        tags = form_data.get("tags", "").strip()
        monitored = form_data.get("monitored") == "on"
        search_for_movie = form_data.get("search_for_movie") == "on"
        enable_scan = form_data.get("enable_scan") == "on"
        enable_automatic_search = form_data.get("enable_automatic_search") == "on"
        enable_integration = form_data.get("enable_integration") == "on"
        
        from ..models.service_instance import RADARR_DEFAULT_SETTINGS
        settings = RADARR_DEFAULT_SETTINGS.copy()
        settings.update({
            "hostname": radarr_hostname,
            "port": int(radarr_port),
            "use_ssl": use_ssl,
            "base_url": radarr_base_url,
            "quality_profile_id": int(quality_profile_id) if quality_profile_id else None,
            "root_folder_path": root_folder_path if root_folder_path else None,
            "minimum_availability": minimum_availability,
            "tags": [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else [],
            "monitored": monitored,
            "search_for_movie": search_for_movie,
            "enable_scan": enable_scan,
            "enable_automatic_search": enable_automatic_search,
            "enable_integration": enable_integration
        })
        instance.set_settings(settings)
        
        # Save to database
        session.add(instance)
        session.commit()
        
        # Get current base_url for HTML responses  
        current_base_url = SettingsService.get_base_url(session)
        
        # Close modal and refresh list
        return HTMLResponse(f'''
            <div class="p-3 bg-green-50 border border-green-200 rounded-md mb-4">
                <p class="text-green-800 text-sm font-medium">✓ Radarr instance "{radarr_name}" updated successfully!</p>
            </div>
            <script>
                // Close modal
                hideServiceModal();
                // Refresh the instances list
                htmx.ajax('GET', '{current_base_url}/admin/services/radarr/list', {{
                    target: '#radarr-instances',
                    swap: 'innerHTML'
                }});
            </script>
        ''')
        
    except Exception as e:
        logger.error(f"Error updating Radarr instance: {e}")
        return HTMLResponse(f'''
            <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                <p class="text-red-808 text-sm">✗ Error updating instance: {str(e)}</p>
            </div>
        ''')


@router.patch("/services/radarr/{instance_id}/update")
async def patch_radarr_integration(
    instance_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Update Radarr integration setting"""
    try:
        from sqlmodel import select
        from ..models.service_instance import ServiceInstance, ServiceType
        
        # Get the instance
        statement = select(ServiceInstance).where(
            ServiceInstance.id == instance_id,
            ServiceInstance.service_type == ServiceType.RADARR
        )
        instance = session.exec(statement).first()
        
        if not instance:
            return JSONResponse(
                status_code=404,
                content={"error": "Radarr instance not found"}
            )
        
        # Parse JSON body
        body = await request.json()
        enable_integration = body.get('enable_integration', True)
        
        # Update settings
        settings = instance.get_settings()
        settings['enable_integration'] = enable_integration
        instance.set_settings(settings)
        
        # Save to database
        session.add(instance)
        session.commit()
        
        return JSONResponse({"success": True, "enable_integration": enable_integration})
        
    except Exception as e:
        print(f"Error updating Radarr integration: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@router.get("/services/radarr/add", response_class=HTMLResponse)
async def add_radarr_form(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get Radarr instance add form"""
    current_base_url = SettingsService.get_base_url(session)
    
    return HTMLResponse(f'''
        <div>
            <h4 class="text-lg font-medium text-gray-900 mb-6">Add Radarr Instance</h4>
            <form hx-post="{current_base_url}/admin/services/radarr/create" hx-target="#radarr-instances" class="space-y-6">
                
                <!-- Instance Name -->
                <div>
                    <label for="radarr_name" class="block text-sm font-medium text-gray-700 mb-2">Instance Name</label>
                    <input type="text" name="radarr_name" id="radarr_name" 
                           placeholder="e.g., Radarr 4K, Movies HD"
                           class="block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                    <p class="mt-1 text-xs text-gray-500">Friendly name to identify this instance</p>
                </div>
                
                <!-- Connection Settings -->
                <div>
                    <h5 class="text-md font-semibold text-gray-900 mb-4">Connection Settings</h5>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                            <label for="radarr_hostname" class="block text-sm font-medium text-gray-700">Hostname/IP</label>
                            <input type="text" name="radarr_hostname" id="radarr_hostname" 
                                   placeholder="172.20.0.11 or localhost"
                                   class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                            <p class="mt-1 text-xs text-gray-500">Server hostname or IP address</p>
                        </div>
                        
                        <div>
                            <label for="radarr_port" class="block text-sm font-medium text-gray-700">Port</label>
                            <input type="number" name="radarr_port" id="radarr_port" 
                                   value="7878"
                                   min="1" max="65535"
                                   class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                            <p class="mt-1 text-xs text-gray-500">Default: 7878</p>
                        </div>
                        
                        <div class="flex items-end">
                            <div class="flex items-center h-10">
                                <input type="checkbox" name="use_ssl" id="use_ssl" 
                                       class="h-4 w-4 text-orange-600 border-gray-300 rounded">
                                <label for="use_ssl" class="ml-2 text-sm text-gray-700">Use HTTPS</label>
                            </div>
                        </div>
                    </div>
                    
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                        <div>
                            <label for="radarr_api_key" class="block text-sm font-medium text-gray-700">API Key</label>
                            <input type="password" name="radarr_api_key" id="radarr_api_key" 
                                   placeholder="Your Radarr API key"
                                   class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                            <p class="mt-1 text-xs text-gray-500">Found in Radarr Settings → General → Security</p>
                        </div>
                        
                        <div>
                            <label for="radarr_base_url" class="block text-sm font-medium text-gray-700">Base URL</label>
                            <input type="text" name="radarr_base_url" id="radarr_base_url" 
                                   placeholder="/radarr (optional)"
                                   class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                            <p class="mt-1 text-xs text-gray-500">For reverse proxy setups</p>
                        </div>
                    </div>
                </div>
                
                <!-- Test Connection -->
                <div>
                    <button type="button" 
                            hx-post="{current_base_url}/admin/services/radarr/test" 
                            hx-target="#test-results"
                            hx-include="form"
                            class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-md text-sm font-medium">
                        <svg class="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                        Test Connection
                    </button>
                    <div id="test-results" class="mt-4"></div>
                </div>
                
                <!-- Advanced Settings (Collapsed by default) -->
                <div class="border-t pt-4">
                    <button type="button" onclick="toggleAdvancedSettings()" 
                            class="flex items-center justify-between w-full text-left focus:outline-none">
                        <h5 class="text-md font-semibold text-gray-900">Advanced Settings</h5>
                        <svg id="advanced-chevron" class="w-5 h-5 text-gray-500 transform transition-transform duration-200" 
                             fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                        </svg>
                    </button>
                    
                    <div id="radarr-advanced-settings" class="hidden mt-4 space-y-4">
                        <!-- Default Settings -->
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label for="radarr_quality_profile_id" class="block text-sm font-medium text-gray-700">Quality Profile</label>
                                <select name="radarr_quality_profile_id" id="radarr_quality_profile_id" 
                                        class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                                    <option value="">Test connection to load profiles</option>
                                </select>
                            </div>
                            
                            <div>
                                <label for="radarr_root_folder_path" class="block text-sm font-medium text-gray-700">Root Folder</label>
                                <select name="radarr_root_folder_path" id="radarr_root_folder_path" 
                                        class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                                    <option value="">Test connection to load folders</option>
                                </select>
                            </div>
                            
                            <div>
                                <label for="minimum_availability" class="block text-sm font-medium text-gray-700">Minimum Availability</label>
                                <select name="minimum_availability" id="minimum_availability" 
                                        class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                                    <option value="announced">Announced</option>
                                    <option value="inCinemas">In Cinemas</option>
                                    <option value="released" selected>Released</option>
                                    <option value="preDB">PreDB</option>
                                </select>
                            </div>
                            
                            <div>
                                <label for="tags" class="block text-sm font-medium text-gray-700">Tags</label>
                                <input type="text" name="tags" id="tags" 
                                       placeholder="4k, uhd, remux (comma separated)"
                                       class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                                <p class="mt-1 text-xs text-gray-500">Optional tags to apply to requests</p>
                            </div>
                        </div>
                        
                        <!-- Checkboxes -->
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4">
                            <div class="flex items-center">
                                <input type="checkbox" name="is_default" id="is_default" 
                                       class="h-4 w-4 text-orange-600 border-gray-300 rounded">
                                <label for="is_default" class="ml-2 text-sm text-gray-700">
                                    Default instance for movie requests
                                </label>
                            </div>
                            
                            <div class="flex items-center">
                                <input type="checkbox" name="enable_scan" id="enable_scan" checked
                                       class="h-4 w-4 text-orange-600 border-gray-300 rounded">
                                <label for="enable_scan" class="ml-2 text-sm text-gray-700">
                                    Enable library scanning
                                </label>
                            </div>
                            
                            <div class="flex items-center">
                                <input type="checkbox" name="enable_automatic_search" id="enable_automatic_search" 
                                       checked
                                       class="h-4 w-4 text-orange-600 border-gray-300 rounded">
                                <label for="enable_automatic_search" class="ml-2 text-sm text-gray-700">
                                    Enable automatic search on approval
                                </label>
                            </div>
                            
                            <div class="flex items-center mt-3">
                                <input type="checkbox" name="enable_integration" id="enable_integration" 
                                       checked
                                       class="h-4 w-4 text-orange-600 border-gray-300 rounded">
                                <label for="enable_integration" class="ml-2 text-sm text-gray-700">
                                    Enable automatic integration (send approved requests to Radarr)
                                </label>
                            </div>
                        </div>
                        
                        <!-- External URL -->
                        <div class="pt-4">
                            <label for="external_url" class="block text-sm font-medium text-gray-700">External URL</label>
                            <input type="url" name="external_url" id="external_url" 
                                   placeholder="https://radarr.yourdomain.com (optional)"
                                   class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-orange-500 focus:border-orange-500">
                            <p class="mt-1 text-xs text-gray-500">Public URL for external access</p>
                        </div>
                    </div>
                </div>
                
                <!-- Buttons -->
                <div class="flex justify-end pt-6 border-t space-x-3">
                    <button type="button" onclick="hideServiceModal()"
                            class="bg-gray-300 hover:bg-gray-400 text-gray-700 px-4 py-2 rounded-md text-sm font-medium">
                        Cancel
                    </button>
                    <button type="submit"
                            class="bg-orange-600 hover:bg-orange-700 text-white px-4 py-2 rounded-md text-sm font-medium">
                        Add Radarr Instance
                    </button>
                </div>
            </form>
        </div>
        
        <script>
        function toggleAdvancedSettings() {{
            const settings = document.getElementById('radarr-advanced-settings');
            const chevron = document.getElementById('advanced-chevron');
            
            if (settings.classList.contains('hidden')) {{
                settings.classList.remove('hidden');
                chevron.style.transform = 'rotate(180deg)';
            }} else {{
                settings.classList.add('hidden');
                chevron.style.transform = 'rotate(0deg)';
            }}
        }}
        </script>
    ''')


@router.post("/services/radarr/test", response_class=HTMLResponse)
async def test_radarr_connection(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Test Radarr connection and load profiles/folders"""
    try:
        form_data = await request.form()
        radarr_name = form_data.get("radarr_name", "").strip()
        radarr_hostname = form_data.get("radarr_hostname", "").strip()
        radarr_port = form_data.get("radarr_port", "7878").strip()
        radarr_api_key = form_data.get("radarr_api_key", "").strip()
        use_ssl = form_data.get("use_ssl") == "on"
        radarr_base_url = form_data.get("radarr_base_url", "").strip()
        
        if not radarr_hostname or not radarr_port or not radarr_api_key:
            return HTMLResponse('''
                <div id="test-results" class="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-800 text-sm">✗ Hostname, port, and API key are required</p>
                </div>
            ''')
        
        # Build URL from hostname, port, and SSL settings
        protocol = "https" if use_ssl else "http"
        radarr_url = f"{protocol}://{radarr_hostname}:{radarr_port}"
        
        # Create temporary ServiceInstance for testing
        from ..models.service_instance import ServiceInstance, ServiceType, RADARR_DEFAULT_SETTINGS
        temp_instance = ServiceInstance(
            name=radarr_name or "Test Instance",
            service_type=ServiceType.RADARR,
            url=radarr_url,
            api_key=radarr_api_key
        )
        
        # Set connection settings
        settings = RADARR_DEFAULT_SETTINGS.copy()
        settings.update({
            "hostname": radarr_hostname,
            "port": int(radarr_port),
            "use_ssl": use_ssl,
            "base_url": radarr_base_url
        })
        temp_instance.set_settings(settings)
        
        # Test the connection
        result = await temp_instance.test_connection()
        
        if result.get('status') == 'connected':
            # Fetch quality profiles and root folders
            try:
                import requests
                base_url = radarr_url.rstrip('/')
                if radarr_base_url:
                    base_url = f"{base_url}/{radarr_base_url.strip('/')}"
                
                # Get quality profiles
                profiles_response = requests.get(
                    f"{base_url}/api/v3/qualityprofile",
                    headers={'X-Api-Key': radarr_api_key},
                    timeout=10,
                    verify=False
                )
                quality_profiles = profiles_response.json() if profiles_response.status_code == 200 else []
                
                # Get root folders
                folders_response = requests.get(
                    f"{base_url}/api/v3/rootfolder", 
                    headers={'X-Api-Key': radarr_api_key},
                    timeout=10,
                    verify=False
                )
                root_folders = folders_response.json() if folders_response.status_code == 200 else []
                
                # Build quality profile options
                profile_options = ""
                for profile in quality_profiles:
                    profile_options += f'<option value="{profile["id"]}">{profile["name"]}</option>'
                
                # Build root folder options
                folder_options = ""
                for folder in root_folders:
                    folder_options += f'<option value="{folder["path"]}">{folder["path"]} ({folder.get("freeSpace", "Unknown")} free)</option>'
                
                # Return success message and populate dropdowns
                return HTMLResponse(f'''
                    <div id="test-results" class="p-3 bg-green-50 border border-green-200 rounded-md mb-4">
                        <p class="text-green-800 text-sm font-medium">✓ Connection successful!</p>
                        <p class="text-green-700 text-xs mt-1">Version: {result.get("version", "Unknown")}</p>
                        <p class="text-green-700 text-xs">Instance: {result.get("instance_name", radarr_name)}</p>
                    </div>
                    <script>
                        // Expand the advanced settings section
                        const advancedSection = document.getElementById('radarr-advanced-settings');
                        const chevron = document.getElementById('advanced-chevron');
                        if (advancedSection && chevron) {{
                            advancedSection.classList.remove('hidden');
                            chevron.classList.add('rotate-180');
                            
                            // Populate quality profiles
                            const qualitySelect = document.getElementById('radarr_quality_profile_id');
                            if (qualitySelect) {{
                                qualitySelect.innerHTML = '<option value="">Select quality profile...</option>{profile_options}';
                            }}
                            
                            // Populate root folders
                            const rootFolderSelect = document.getElementById('radarr_root_folder_path');
                            if (rootFolderSelect) {{
                                rootFolderSelect.innerHTML = '<option value="">Select root folder...</option>{folder_options}';
                            }}
                        }}
                    </script>
                ''')
                
            except Exception as e:
                # Connection worked but couldn't fetch additional data
                return HTMLResponse(f'''
                    <div id="test-results" class="p-3 bg-yellow-50 border border-yellow-200 rounded-md mb-4">
                        <p class="text-yellow-800 text-sm font-medium">✓ Connection successful!</p>
                        <p class="text-yellow-700 text-xs mt-1">Version: {result.get("version", "Unknown")}</p>
                        <p class="text-yellow-700 text-xs">Warning: Could not load profiles/folders: {str(e)}</p>
                    </div>
                    <script>
                        // Expand the advanced settings section anyway
                        const advancedSection = document.getElementById('radarr-advanced-settings');
                        const chevron = document.getElementById('advanced-chevron');
                        if (advancedSection && chevron) {{
                            advancedSection.classList.remove('hidden');
                            chevron.classList.add('rotate-180');
                        }}
                    </script>
                ''')
        else:
            error_msg = result.get('message', 'Connection failed')
            return HTMLResponse(f'''
                <div id="test-results" class="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-800 text-sm">✗ Connection failed: {error_msg}</p>
                </div>
            ''')
            
    except Exception as e:
        logger.error(f"Error testing Radarr connection: {e}")
        return HTMLResponse(f'''
            <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                <p class="text-red-800 text-sm">✗ Error testing connection: {str(e)}</p>
            </div>
        ''')


@router.post("/services/radarr/create", response_class=HTMLResponse)
async def create_radarr_instance(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Create a new Radarr instance"""
    try:
        form_data = await request.form()
        
        # Extract form data
        radarr_name = form_data.get("radarr_name", "").strip()
        radarr_hostname = form_data.get("radarr_hostname", "").strip()
        radarr_port = form_data.get("radarr_port", "7878").strip()
        radarr_api_key = form_data.get("radarr_api_key", "").strip()
        use_ssl = form_data.get("use_ssl") == "on"
        radarr_base_url = form_data.get("radarr_base_url", "").strip()
        
        # Advanced settings
        radarr_quality_profile_id = form_data.get("radarr_quality_profile_id", "").strip()
        radarr_root_folder_path = form_data.get("radarr_root_folder_path", "").strip()
        minimum_availability = form_data.get("minimum_availability", "inCinemas").strip()
        tags = form_data.get("tags", "").strip()
        monitored = form_data.get("monitored") == "on"
        search_for_movie = form_data.get("search_for_movie") == "on"
        enable_integration = form_data.get("enable_integration") == "on"
        
        # Validation
        if not radarr_name or not radarr_hostname or not radarr_port or not radarr_api_key:
            return HTMLResponse('''
                <div class="p-3 bg-red-50 border border-red-200 rounded-md mb-4">
                    <p class="text-red-800 text-sm">✗ Instance name, hostname, port, and API key are required</p>
                </div>
            ''')
        
        # Build URL from components
        protocol = "https" if use_ssl else "http"
        radarr_url = f"{protocol}://{radarr_hostname}:{radarr_port}"
        
        # Create ServiceInstance
        from ..models.service_instance import ServiceInstance, ServiceType, RADARR_DEFAULT_SETTINGS
        
        # Prepare settings
        settings = RADARR_DEFAULT_SETTINGS.copy()
        settings.update({
            "hostname": radarr_hostname,
            "port": int(radarr_port),
            "use_ssl": use_ssl,
            "base_url": radarr_base_url,
            "quality_profile_id": int(radarr_quality_profile_id) if radarr_quality_profile_id else None,
            "root_folder_path": radarr_root_folder_path or None,
            "minimum_availability": minimum_availability,
            "tags": [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else [],
            "monitored": monitored,
            "search_for_movie": search_for_movie,
            "enable_scan": True,
            "enable_automatic_search": True,
            "enable_integration": enable_integration
        })
        
        # Create the instance
        new_instance = ServiceInstance(
            name=radarr_name,
            service_type=ServiceType.RADARR,
            url=radarr_url,
            api_key=radarr_api_key,
            is_enabled=True,
            created_by=current_user.id
        )
        new_instance.set_settings(settings)
        
        # Save to database
        session.add(new_instance)
        session.commit()
        session.refresh(new_instance)
        
        # Test the connection
        result = await new_instance.test_connection()
        
        # Get current base_url for HTML responses  
        current_base_url = SettingsService.get_base_url(session)
        
        # Close modal and refresh list
        return HTMLResponse(f'''
            <div class="p-3 bg-green-50 border border-green-200 rounded-md mb-4">
                <p class="text-green-800 text-sm font-medium">✓ Radarr instance "{radarr_name}" created successfully!</p>
            </div>
            <script>
                // Close modal
                hideServiceModal();
                // Refresh the instances list
                htmx.ajax('GET', '{current_base_url}/admin/services/radarr/list', {{
                    target: '#radarr-instances',
                    swap: 'innerHTML'
                }});
            </script>
        ''')
        
    except Exception as e:
        logger.error(f"Error creating Radarr instance: {e}")
        return HTMLResponse(f'''
            <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                <p class="text-red-800 text-sm">✗ Error creating instance: {str(e)}</p>
            </div>
        ''')


@router.post("/services/sonarr/test", response_class=HTMLResponse)
async def test_sonarr_connection(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Test Sonarr connection and load profiles/folders"""
    try:
        form_data = await request.form()
        sonarr_name = form_data.get("sonarr_name", "").strip()
        sonarr_hostname = form_data.get("sonarr_hostname", "").strip()
        sonarr_port = form_data.get("sonarr_port", "8989").strip()
        sonarr_api_key = form_data.get("sonarr_api_key", "").strip()
        use_ssl = form_data.get("use_ssl") == "on"
        sonarr_base_url = form_data.get("sonarr_base_url", "").strip()
        
        if not sonarr_hostname or not sonarr_port or not sonarr_api_key:
            return HTMLResponse('''
                <div id="sonarr-test-results" class="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-800 text-sm">✗ Hostname, port, and API key are required</p>
                </div>
            ''')
        
        # Build URL from hostname, port, and SSL settings
        protocol = "https" if use_ssl else "http"
        sonarr_url = f"{protocol}://{sonarr_hostname}:{sonarr_port}"
        
        # Create temporary ServiceInstance for testing
        from ..models.service_instance import ServiceInstance, ServiceType, SONARR_DEFAULT_SETTINGS
        temp_instance = ServiceInstance(
            name=sonarr_name or "Test Instance",
            service_type=ServiceType.SONARR,
            url=sonarr_url,
            api_key=sonarr_api_key
        )
        
        # Set connection settings
        settings = SONARR_DEFAULT_SETTINGS.copy()
        settings.update({
            "hostname": sonarr_hostname,
            "port": int(sonarr_port),
            "use_ssl": use_ssl,
            "base_url": sonarr_base_url
        })
        temp_instance.set_settings(settings)
        
        # Test the connection
        result = await temp_instance.test_connection()
        
        if result.get('status') == 'connected':
            # Fetch quality profiles, language profiles and root folders
            try:
                import requests
                base_url = sonarr_url.rstrip('/')
                if sonarr_base_url:
                    base_url = f"{base_url}/{sonarr_base_url.strip('/')}"
                
                # Get quality profiles
                profiles_response = requests.get(
                    f"{base_url}/api/v3/qualityprofile",
                    headers={'X-Api-Key': sonarr_api_key},
                    timeout=10,
                    verify=False
                )
                quality_profiles = profiles_response.json() if profiles_response.status_code == 200 else []
                
                # Get language profiles (Sonarr v3)
                language_response = requests.get(
                    f"{base_url}/api/v3/languageprofile",
                    headers={'X-Api-Key': sonarr_api_key},
                    timeout=10,
                    verify=False
                )
                language_profiles = language_response.json() if language_response.status_code == 200 else []
                
                # Get root folders
                folders_response = requests.get(
                    f"{base_url}/api/v3/rootfolder", 
                    headers={'X-Api-Key': sonarr_api_key},
                    timeout=10,
                    verify=False
                )
                root_folders = folders_response.json() if folders_response.status_code == 200 else []
                
                # Build quality profile options
                quality_options = ""
                for profile in quality_profiles:
                    quality_options += f'<option value="{profile["id"]}">{profile["name"]}</option>'
                
                # Build language profile options
                language_options = ""
                for profile in language_profiles:
                    language_options += f'<option value="{profile["id"]}">{profile["name"]}</option>'
                
                # Build root folder options
                folder_options = ""
                for folder in root_folders:
                    folder_options += f'<option value="{folder["path"]}">{folder["path"]} ({folder.get("freeSpace", "Unknown")} free)</option>'
                
                # Return success message and populate dropdowns
                return HTMLResponse(f'''
                    <div id="sonarr-test-results" class="p-3 bg-green-50 border border-green-200 rounded-md mb-4">
                        <p class="text-green-800 text-sm font-medium">✓ Connection successful!</p>
                        <p class="text-green-700 text-xs mt-1">Version: {result.get("version", "Unknown")}</p>
                        <p class="text-green-700 text-xs">Instance: {result.get("instance_name", sonarr_name)}</p>
                    </div>
                    <script>
                        // Expand the advanced settings section
                        const advancedSection = document.getElementById('sonarr-advanced-settings');
                        const chevron = document.getElementById('sonarr-advanced-chevron');
                        if (advancedSection && chevron) {{
                            advancedSection.classList.remove('hidden');
                            chevron.classList.add('rotate-180');
                            
                            // Populate quality profiles
                            const qualitySelect = document.getElementById('sonarr_quality_profile_id');
                            if (qualitySelect) {{
                                qualitySelect.innerHTML = '<option value="">Select quality profile...</option>{quality_options}';
                            }}
                            
                            // Populate language profiles
                            const languageSelect = document.getElementById('sonarr_language_profile_id');
                            if (languageSelect) {{
                                languageSelect.innerHTML = '<option value="">Select language profile...</option>{language_options}';
                            }}
                            
                            // Populate root folders
                            const rootFolderSelect = document.getElementById('sonarr_root_folder_path');
                            if (rootFolderSelect) {{
                                rootFolderSelect.innerHTML = '<option value="">Select root folder...</option>{folder_options}';
                            }}
                        }}
                    </script>
                ''')
                
            except Exception as e:
                # Connection worked but couldn't fetch additional data
                return HTMLResponse(f'''
                    <div id="sonarr-test-results" class="p-3 bg-yellow-50 border border-yellow-200 rounded-md mb-4">
                        <p class="text-yellow-800 text-sm font-medium">✓ Connection successful!</p>
                        <p class="text-yellow-700 text-xs mt-1">Version: {result.get("version", "Unknown")}</p>
                        <p class="text-yellow-700 text-xs">Warning: Could not load profiles/folders: {str(e)}</p>
                    </div>
                    <script>
                        // Expand the advanced settings section anyway
                        const advancedSection = document.getElementById('sonarr-advanced-settings');
                        const chevron = document.getElementById('sonarr-advanced-chevron');
                        if (advancedSection && chevron) {{
                            advancedSection.classList.remove('hidden');
                            chevron.classList.add('rotate-180');
                        }}
                    </script>
                ''')
        else:
            error_msg = result.get('message', 'Connection failed')
            return HTMLResponse(f'''
                <div id="sonarr-test-results" class="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-800 text-sm">✗ Connection failed: {error_msg}</p>
                </div>
            ''')
            
    except Exception as e:
        logger.error(f"Error testing Sonarr connection: {e}")
        return HTMLResponse(f'''
            <div id="sonarr-test-results" class="p-3 bg-red-50 border border-red-200 rounded-md">
                <p class="text-red-800 text-sm">✗ Error testing connection: {str(e)}</p>
            </div>
        ''')


@router.post("/services/sonarr/create", response_class=HTMLResponse)
async def create_sonarr_instance(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Create a new Sonarr instance"""
    try:
        form_data = await request.form()
        
        # Extract form data
        sonarr_name = form_data.get("sonarr_name", "").strip()
        sonarr_hostname = form_data.get("sonarr_hostname", "").strip()
        sonarr_port = form_data.get("sonarr_port", "8989").strip()
        sonarr_api_key = form_data.get("sonarr_api_key", "").strip()
        use_ssl = form_data.get("use_ssl") == "on"
        sonarr_base_url = form_data.get("sonarr_base_url", "").strip()
        
        # Advanced settings
        sonarr_quality_profile_id = form_data.get("sonarr_quality_profile_id", "").strip()
        sonarr_language_profile_id = form_data.get("sonarr_language_profile_id", "").strip()
        sonarr_root_folder_path = form_data.get("sonarr_root_folder_path", "").strip()
        minimum_availability = form_data.get("minimum_availability", "inCinemas").strip()
        tags = form_data.get("tags", "").strip()
        external_url = form_data.get("external_url", "").strip()
        enable_scan = form_data.get("enable_scan") == "on"
        enable_automatic_search = form_data.get("enable_automatic_search") == "on"
        enable_integration = form_data.get("enable_integration") == "on"
        enable_season_folders = form_data.get("enable_season_folders") == "on"
        anime_standard_format = form_data.get("anime_standard_format") == "on"
        
        # Validation
        if not sonarr_name or not sonarr_hostname or not sonarr_port or not sonarr_api_key:
            return HTMLResponse('''
                <div class="p-3 bg-red-50 border border-red-200 rounded-md mb-4">
                    <p class="text-red-800 text-sm">✗ Instance name, hostname, port, and API key are required</p>
                </div>
            ''')
        
        # Build URL from components
        protocol = "https" if use_ssl else "http"
        sonarr_url = f"{protocol}://{sonarr_hostname}:{sonarr_port}"
        
        # Create ServiceInstance
        from ..models.service_instance import ServiceInstance, ServiceType, SONARR_DEFAULT_SETTINGS
        
        # Prepare settings
        settings = SONARR_DEFAULT_SETTINGS.copy()
        settings.update({
            "hostname": sonarr_hostname,
            "port": int(sonarr_port),
            "use_ssl": use_ssl,
            "base_url": sonarr_base_url,
            "quality_profile_id": int(sonarr_quality_profile_id) if sonarr_quality_profile_id else None,
            "language_profile_id": int(sonarr_language_profile_id) if sonarr_language_profile_id else None,
            "root_folder_path": sonarr_root_folder_path or None,
            "minimum_availability": minimum_availability,
            "tags": [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else [],
            "external_url": external_url,
            "enable_scan": enable_scan,
            "enable_automatic_search": enable_automatic_search,
            "enable_integration": enable_integration,
            "season_folder": enable_season_folders,
            "anime_standard_format": anime_standard_format
        })
        
        # Create the instance
        new_instance = ServiceInstance(
            name=sonarr_name,
            service_type=ServiceType.SONARR,
            url=sonarr_url,
            api_key=sonarr_api_key,
            is_enabled=True,
            created_by=current_user.id
        )
        new_instance.set_settings(settings)
        
        # Save to database
        session.add(new_instance)
        session.commit()
        session.refresh(new_instance)
        
        # Test the connection
        result = await new_instance.test_connection()
        
        # Get current base_url for HTML responses  
        current_base_url = SettingsService.get_base_url(session)
        
        # Close modal and refresh list
        return HTMLResponse(f'''
            <div class="p-3 bg-green-50 border border-green-200 rounded-md mb-4">
                <p class="text-green-800 text-sm font-medium">✓ Sonarr instance "{sonarr_name}" created successfully!</p>
            </div>
            <script>
                // Close modal
                hideServiceModal();
                // Refresh the instances list
                htmx.ajax('GET', '{current_base_url}/admin/services/sonarr/list', {{
                    target: '#sonarr-instances',
                    swap: 'innerHTML'
                }});
            </script>
        ''')
        
    except Exception as e:
        logger.error(f"Error creating Sonarr instance: {e}")
        return HTMLResponse(f'''
            <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                <p class="text-red-800 text-sm">✗ Error creating instance: {str(e)}</p>
            </div>
        ''')


@router.delete("/services/radarr/{instance_id}", response_class=HTMLResponse)
async def delete_radarr_instance(
    instance_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Delete a Radarr instance"""
    try:
        from sqlmodel import select
        from ..models.service_instance import ServiceInstance, ServiceType
        
        # Get the instance
        statement = select(ServiceInstance).where(
            ServiceInstance.id == instance_id,
            ServiceInstance.service_type == ServiceType.RADARR
        )
        instance = session.exec(statement).first()
        
        if not instance:
            return HTMLResponse('''
                <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-800 text-sm">✗ Radarr instance not found</p>
                </div>
            ''')
        
        # Delete the instance
        session.delete(instance)
        session.commit()
        
        # Return updated list
        return await list_radarr_instances(request, current_user, session)
        
    except Exception as e:
        logger.error(f"Error deleting Radarr instance: {e}")
        return HTMLResponse(f'''
            <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                <p class="text-red-800 text-sm">✗ Error deleting instance: {str(e)}</p>
            </div>
        ''')


@router.post("/services/radarr/{instance_id}/test", response_class=HTMLResponse)
async def test_radarr_instance(
    instance_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Test connection for a specific Radarr instance"""
    try:
        from sqlmodel import select
        from ..models.service_instance import ServiceInstance, ServiceType
        
        # Get the instance
        statement = select(ServiceInstance).where(
            ServiceInstance.id == instance_id,
            ServiceInstance.service_type == ServiceType.RADARR
        )
        instance = session.exec(statement).first()
        
        if not instance:
            return HTMLResponse('''
                <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-800 text-sm">✗ Radarr instance not found</p>
                </div>
            ''')
        
        # Test the connection
        result = await instance.test_connection()
        
        # Update the instance in database
        session.add(instance)
        session.commit()
        
        if result.get('status') == 'connected':
            return HTMLResponse(f'''
                <div class="p-3 bg-green-50 border border-green-200 rounded-md">
                    <p class="text-green-800 text-sm font-medium">✓ Connection successful!</p>
                    <p class="text-green-700 text-xs mt-1">Version: {result.get("version", "Unknown")}</p>
                </div>
            ''')
        else:
            error_msg = result.get('message', 'Connection failed')
            return HTMLResponse(f'''
                <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-800 text-sm">✗ Connection failed: {error_msg}</p>
                </div>
            ''')
            
    except Exception as e:
        logger.error(f"Error testing Radarr instance: {e}")
        return HTMLResponse(f'''
            <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                <p class="text-red-800 text-sm">✗ Error testing connection: {str(e)}</p>
            </div>
        ''')


# Sonarr Service Endpoints  
@router.get("/services/sonarr/list", response_class=HTMLResponse)
async def list_sonarr_instances(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """List all Sonarr instances"""
    from sqlmodel import select
    from ..models.service_instance import ServiceInstance, ServiceType
    
    # Get all Sonarr instances from database
    statement = select(ServiceInstance).where(ServiceInstance.service_type == ServiceType.SONARR)
    instances = session.exec(statement).all()
    
    if not instances:
        return HTMLResponse('''
            <div class="p-6 text-center text-gray-500">
                <svg class="w-12 h-12 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
                </svg>
                <p class="text-sm">No Sonarr instances configured</p>
                <p class="text-xs text-gray-400 mt-1">Add an instance to get started with TV show automation</p>
            </div>
        ''')
    
    # Get current base_url for HTML responses  
    current_base_url = SettingsService.get_base_url(session)
    
    # Build HTML for each instance
    instances_html = ""
    for instance in instances:
        # Test connection automatically to get current status
        try:
            current_result = await instance.test_connection()
            # Save the updated test result
            session.add(instance)
            session.commit()
            test_result = current_result
        except Exception as e:
            print(f"Error testing Sonarr {instance.name}: {e}")
            test_result = instance.get_test_result()
        
        status_color = "green" if test_result.get("status") == "connected" else "red"
        status_text = "Connected" if test_result.get("status") == "connected" else "Disconnected"
        
        # Get settings for display
        settings = instance.get_settings()
        hostname = settings.get("hostname", "Unknown")
        port = settings.get("port", "Unknown")
        use_ssl = settings.get("use_ssl", False)
        protocol = "HTTPS" if use_ssl else "HTTP"
        enable_integration = settings.get('enable_integration', True)
        
        instances_html += f'''
            <div class="p-4 border-b border-gray-200 last:border-b-0">
                <div class="flex items-center justify-between">
                    <div class="flex-1">
                        <div class="flex items-center">
                            <h4 class="text-lg font-medium text-gray-900">{instance.name}</h4>
                            <span class="ml-3 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-{status_color}-100 text-{status_color}-800">
                                <div class="w-2 h-2 bg-{status_color}-400 rounded-full mr-1"></div>
                                {status_text}
                            </span>
                        </div>
                        <div class="mt-1 text-sm text-gray-500">
                            <span>{protocol}://{hostname}:{port}</span>
                            {f' • Version: {test_result.get("version", "Unknown")}' if test_result.get("version") else ''}
                        </div>
                        <div class="mt-1 text-xs text-gray-400">
                            Created: {instance.created_at.strftime("%Y-%m-%d %H:%M") if instance.created_at else "Unknown"}
                            {f' • Last tested: {instance.last_tested_at.strftime("%Y-%m-%d %H:%M")}' if instance.last_tested_at else ''}
                        </div>
                        <div class="mt-2 flex items-center">
                            <span class="text-xs text-gray-600 mr-2">Integration:</span>
                            <button type="button"
                                    onclick="toggleServiceIntegration({instance.id}, 'sonarr', this)"
                                    data-enabled="{'true' if enable_integration else 'false'}"
                                    class="relative inline-flex h-4 w-7 items-center rounded-full transition-colors focus:outline-none focus:ring-1 focus:ring-blue-500 focus:ring-offset-1 {'bg-blue-600' if enable_integration else 'bg-gray-300'}">
                                <span class="inline-block h-3 w-3 transform rounded-full bg-white transition-transform {'translate-x-3.5' if enable_integration else 'translate-x-0.5'}"></span>
                            </button>
                        </div>
                    </div>
                    <div class="flex items-center space-x-2">
                        <button type="button" 
                                hx-post="{current_base_url}/admin/services/sonarr/{instance.id}/test"
                                hx-target="#instance-{instance.id}-status"
                                class="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-xs font-medium">
                            Test
                        </button>
                        <button type="button" 
                                hx-get="{current_base_url}/admin/services/sonarr/{instance.id}/edit"
                                hx-target="#service-modal-content"
                                onclick="showServiceModal('Edit Sonarr Instance')"
                                class="bg-gray-600 hover:bg-gray-700 text-white px-3 py-1 rounded text-xs font-medium">
                            Edit
                        </button>
                        <button type="button" 
                                hx-delete="{current_base_url}/admin/services/sonarr/{instance.id}"
                                hx-target="#sonarr-instances"
                                hx-confirm="Are you sure you want to delete this Sonarr instance?"
                                class="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded text-xs font-medium">
                            Delete
                        </button>
                    </div>
                </div>
                <div id="instance-{instance.id}-status" class="mt-2"></div>
            </div>
        '''
    
    return HTMLResponse(instances_html)


@router.delete("/services/sonarr/{instance_id}", response_class=HTMLResponse)
async def delete_sonarr_instance(
    instance_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Delete a Sonarr instance"""
    try:
        from sqlmodel import select
        from ..models.service_instance import ServiceInstance, ServiceType
        
        # Get the instance
        statement = select(ServiceInstance).where(
            ServiceInstance.id == instance_id,
            ServiceInstance.service_type == ServiceType.SONARR
        )
        instance = session.exec(statement).first()
        
        if not instance:
            return HTMLResponse('''
                <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-800 text-sm">✗ Sonarr instance not found</p>
                </div>
            ''')
        
        # Delete the instance
        session.delete(instance)
        session.commit()
        
        # Return updated list
        return await list_sonarr_instances(request, current_user, session)
        
    except Exception as e:
        logger.error(f"Error deleting Sonarr instance: {e}")
        return HTMLResponse(f'''
            <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                <p class="text-red-800 text-sm">✗ Error deleting instance: {str(e)}</p>
            </div>
        ''')


@router.post("/services/sonarr/{instance_id}/test", response_class=HTMLResponse)
async def test_sonarr_instance(
    instance_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Test connection for a specific Sonarr instance"""
    try:
        from sqlmodel import select
        from ..models.service_instance import ServiceInstance, ServiceType
        
        # Get the instance
        statement = select(ServiceInstance).where(
            ServiceInstance.id == instance_id,
            ServiceInstance.service_type == ServiceType.SONARR
        )
        instance = session.exec(statement).first()
        
        if not instance:
            return HTMLResponse('''
                <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-800 text-sm">✗ Sonarr instance not found</p>
                </div>
            ''')
        
        # Test the connection
        result = await instance.test_connection()
        
        # Update the instance in database
        session.add(instance)
        session.commit()
        
        if result.get('status') == 'connected':
            return HTMLResponse(f'''
                <div class="p-3 bg-green-50 border border-green-200 rounded-md">
                    <p class="text-green-800 text-sm font-medium">✓ Connection successful!</p>
                    <p class="text-green-700 text-xs mt-1">Version: {result.get("version", "Unknown")}</p>
                </div>
            ''')
        else:
            error_msg = result.get('message', 'Connection failed')
            return HTMLResponse(f'''
                <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-800 text-sm">✗ Connection failed: {error_msg}</p>
                </div>
            ''')
            
    except Exception as e:
        logger.error(f"Error testing Sonarr instance: {e}")
        return HTMLResponse(f'''
            <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                <p class="text-red-800 text-sm">✗ Error testing connection: {str(e)}</p>
            </div>
        ''')


@router.get("/services/sonarr/{instance_id}/edit", response_class=HTMLResponse)
async def edit_sonarr_form(
    instance_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get Sonarr instance edit form with existing data"""
    try:
        from sqlmodel import select
        from ..models.service_instance import ServiceInstance, ServiceType
        
        # Get the instance
        statement = select(ServiceInstance).where(
            ServiceInstance.id == instance_id,
            ServiceInstance.service_type == ServiceType.SONARR
        )
        instance = session.exec(statement).first()
        
        if not instance:
            return HTMLResponse('''
                <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-800 text-sm">✗ Sonarr instance not found</p>
                </div>
            ''')
        
        # Get current base_url for HTML responses  
        current_base_url = SettingsService.get_base_url(session)
        
        # Get instance settings
        settings = instance.get_settings()
        hostname = settings.get("hostname", "")
        port = settings.get("port", 8989)
        use_ssl = settings.get("use_ssl", False)
        base_url = settings.get("base_url", "")
        quality_profile_id = settings.get("quality_profile_id", "")
        language_profile_id = settings.get("language_profile_id", "")
        root_folder_path = settings.get("root_folder_path", "")
        minimum_availability = settings.get("minimum_availability", "inCinemas")
        monitored = settings.get("monitored", True)
        season_folder = settings.get("season_folder", True)
        search_for_missing = settings.get("search_for_missing_episodes", True)
        enable_scan = settings.get("enable_scan", True)
        enable_automatic_search = settings.get("enable_automatic_search", True)
        enable_integration = settings.get("enable_integration", True)
        tags = settings.get("tags", [])
        
        # Try to fetch current quality profiles and root folders from Sonarr
        quality_profiles_html = '<option value="">Select quality profile...</option>'
        root_folders_html = '<option value="">Select root folder...</option>'
        
        try:
            from ..services.sonarr_service import SonarrService
            sonarr_service = SonarrService(session)
            
            # Set the service to use this specific instance
            sonarr_service.instance = instance
            sonarr_service.base_url = instance.url
            sonarr_service.api_key = instance.api_key
            sonarr_service.headers = {
                'X-Api-Key': instance.api_key,
                'Content-Type': 'application/json'
            } if instance.api_key else {}
            
            # Fetch quality profiles
            profiles = await sonarr_service.get_quality_profiles()
            for profile in profiles:
                selected = 'selected' if str(profile.get('id')) == str(quality_profile_id) else ''
                quality_profiles_html += f'<option value="{profile.get("id")}" {selected}>{profile.get("name", "Unknown")}</option>'
            
            # Fetch root folders  
            folders = await sonarr_service.get_root_folders()
            for folder in folders:
                selected = 'selected' if folder.get('path') == root_folder_path else ''
                root_folders_html += f'<option value="{folder.get("path")}" {selected}>{folder.get("path")}</option>'
                
        except Exception as e:
            print(f"Could not fetch Sonarr data for edit form: {e}")
            # Fallback to showing saved values if service is unreachable
            if quality_profile_id:
                quality_profiles_html += f'<option value="{quality_profile_id}" selected>Profile ID {quality_profile_id} (Saved)</option>'
            if root_folder_path:
                root_folders_html += f'<option value="{root_folder_path}" selected>{root_folder_path} (Saved)</option>'
        
        return HTMLResponse(f'''
            <div>
                <h4 class="text-lg font-medium text-gray-900 mb-6">Edit Sonarr Instance</h4>
                <form hx-post="{current_base_url}/admin/services/sonarr/{instance_id}/update" hx-target="#sonarr-instances" class="space-y-6">
                    
                    <!-- Instance Name -->
                    <div>
                        <label for="sonarr_name" class="block text-sm font-medium text-gray-700 mb-2">Instance Name</label>
                        <input type="text" name="sonarr_name" id="sonarr_name" 
                               value="{instance.name}"
                               placeholder="e.g., Sonarr 4K, TV Shows HD"
                               class="block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                    </div>
                    
                    <!-- Connection Settings -->
                    <div>
                        <h5 class="text-md font-semibold text-gray-900 mb-4">Connection Settings</h5>
                        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div>
                                <label for="sonarr_hostname" class="block text-sm font-medium text-gray-700">Hostname/IP</label>
                                <input type="text" name="sonarr_hostname" id="sonarr_hostname" 
                                       value="{hostname}"
                                       placeholder="172.20.0.11 or localhost"
                                       class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                            </div>
                            
                            <div>
                                <label for="sonarr_port" class="block text-sm font-medium text-gray-700">Port</label>
                                <input type="number" name="sonarr_port" id="sonarr_port" 
                                       value="{port}"
                                       min="1" max="65535"
                                       class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                            </div>
                            
                            <div class="flex items-end">
                                <div class="flex items-center h-10">
                                    <input type="checkbox" name="use_ssl" id="sonarr_use_ssl" 
                                           {"checked" if use_ssl else ""}
                                           class="h-4 w-4 text-purple-600 border-gray-300 rounded">
                                    <label for="sonarr_use_ssl" class="ml-2 text-sm text-gray-700">Use HTTPS</label>
                                </div>
                            </div>
                        </div>
                        
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                            <div>
                                <label for="sonarr_api_key" class="block text-sm font-medium text-gray-700">API Key</label>
                                <input type="password" name="sonarr_api_key" id="sonarr_api_key" 
                                       value="{instance.api_key}"
                                       placeholder="Your Sonarr API key"
                                       class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                            </div>
                            
                            <div>
                                <label for="sonarr_base_url" class="block text-sm font-medium text-gray-700">Base URL</label>
                                <input type="text" name="sonarr_base_url" id="sonarr_base_url" 
                                       value="{base_url}"
                                       placeholder="/sonarr (optional)"
                                       class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                            </div>
                        </div>
                    </div>
                    
                    <!-- Test Connection -->
                    <div>
                        <button type="button" 
                                hx-post="{current_base_url}/admin/services/sonarr/test" 
                                hx-target="#sonarr-test-results"
                                hx-include="form"
                                class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-md text-sm font-medium">
                            <svg class="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                            </svg>
                            Test Connection
                        </button>
                        <div id="sonarr-test-results" class="mt-4"></div>
                    </div>
                    
                    <!-- Advanced Settings -->
                    <div class="border-t pt-4">
                        <button type="button" onclick="toggleSonarrAdvancedSettings()" 
                                class="flex items-center justify-between w-full text-left focus:outline-none">
                            <h5 class="text-md font-semibold text-gray-900">Advanced Settings</h5>
                            <svg id="sonarr-advanced-chevron" class="w-5 h-5 text-gray-500 transform transition-transform duration-200" 
                                 fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                            </svg>
                        </button>
                        
                        <div id="sonarr-advanced-settings" class="mt-4 space-y-4">
                            <!-- Default Settings -->
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div>
                                    <label for="sonarr_quality_profile_id" class="block text-sm font-medium text-gray-700">Quality Profile</label>
                                    <select name="sonarr_quality_profile_id" id="sonarr_quality_profile_id" 
                                            class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                                        {quality_profiles_html}
                                    </select>
                                </div>
                                
                                <div>
                                    <label for="sonarr_language_profile_id" class="block text-sm font-medium text-gray-700">Language Profile</label>
                                    <select name="sonarr_language_profile_id" id="sonarr_language_profile_id" 
                                            class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                                        <option value="">Select language profile...</option>
                                        {f'<option value="{language_profile_id}" selected>Language ID {language_profile_id}</option>' if language_profile_id else ''}
                                    </select>
                                </div>
                                
                                <div>
                                    <label for="sonarr_root_folder_path" class="block text-sm font-medium text-gray-700">Root Folder</label>
                                    <select name="sonarr_root_folder_path" id="sonarr_root_folder_path" 
                                            class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                                        {root_folders_html}
                                    </select>
                                </div>
                                
                                <div>
                                    <label for="tags" class="block text-sm font-medium text-gray-700">Tags</label>
                                    <input type="text" name="tags" id="tags" 
                                           value="{', '.join(tags) if isinstance(tags, list) else tags}"
                                           placeholder="4k, uhd, anime (comma separated)"
                                           class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                                    <p class="mt-1 text-xs text-gray-500">Optional tags to apply to requests</p>
                                </div>
                            </div>
                            
                            <!-- Advanced Settings (match add form exactly) -->
                            <div class="border-t pt-6">
                                <h5 class="text-md font-medium text-gray-900 mb-4">Advanced Settings</h5>
                                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    <div class="flex items-center">
                                        <input type="checkbox" name="enable_scan" id="enable_scan" 
                                               {"checked" if enable_scan else ""}
                                               class="h-4 w-4 text-purple-600 border-gray-300 rounded">
                                        <label for="enable_scan" class="ml-2 text-sm text-gray-700">
                                            Enable library scanning
                                        </label>
                                    </div>
                                    
                                    <div class="flex items-center">
                                        <input type="checkbox" name="enable_automatic_search" id="enable_automatic_search" 
                                               {"checked" if enable_automatic_search else ""}
                                               class="h-4 w-4 text-purple-600 border-gray-300 rounded">
                                        <label for="enable_automatic_search" class="ml-2 text-sm text-gray-700">
                                            Enable automatic search on approval
                                        </label>
                                    </div>
                                    
                                    <div class="flex items-center">
                                        <input type="checkbox" name="enable_integration" id="enable_integration" 
                                               {"checked" if enable_integration else ""}
                                               class="h-4 w-4 text-purple-600 border-gray-300 rounded">
                                        <label for="enable_integration" class="ml-2 text-sm text-gray-700">
                                            Enable automatic integration (send approved requests to Sonarr)
                                        </label>
                                    </div>
                                    
                                    <div class="flex items-center">
                                        <input type="checkbox" name="enable_season_folders" id="enable_season_folders" 
                                               {"checked" if season_folder else ""}
                                               class="h-4 w-4 text-purple-600 border-gray-300 rounded">
                                        <label for="enable_season_folders" class="ml-2 text-sm text-gray-700">
                                            Enable season folders
                                        </label>
                                    </div>
                                    
                                    <div class="flex items-center">
                                        <input type="checkbox" name="anime_standard_format" id="anime_standard_format"
                                               {"checked" if settings.get('anime_standard_format', False) else ""}
                                               class="h-4 w-4 text-purple-600 border-gray-300 rounded">
                                        <label for="anime_standard_format" class="ml-2 text-sm text-gray-700">
                                            Use anime standard format
                                        </label>
                                    </div>
                                </div>
                                
                                <div class="mt-4">
                                    <label for="external_url" class="block text-sm font-medium text-gray-700">External URL</label>
                                    <input type="url" name="external_url" id="external_url" 
                                           value="{settings.get('external_url', '')}"
                                           placeholder="https://sonarr.yourdomain.com (optional)"
                                           class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                                    <p class="mt-1 text-xs text-gray-500">Public URL for external access</p>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Form Actions -->
                    <div class="flex justify-end space-x-3 pt-6 border-t">
                        <button type="button" onclick="hideServiceModal()"
                                class="bg-gray-300 hover:bg-gray-400 text-gray-700 px-4 py-2 rounded-md text-sm font-medium">
                            Cancel
                        </button>
                        <button type="submit" 
                                class="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-md text-sm font-medium">
                            Update Instance
                        </button>
                    </div>
                </form>
            </div>
        ''')
        
    except Exception as e:
        logger.error(f"Error loading Sonarr edit form: {e}")
        return HTMLResponse(f'''
            <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                <p class="text-red-800 text-sm">✗ Error loading edit form: {str(e)}</p>
            </div>
        ''')


@router.post("/services/sonarr/{instance_id}/update", response_class=HTMLResponse)
async def update_sonarr_instance(
    instance_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Update an existing Sonarr instance"""
    try:
        from sqlmodel import select
        from ..models.service_instance import ServiceInstance, ServiceType
        
        # Get the instance
        statement = select(ServiceInstance).where(
            ServiceInstance.id == instance_id,
            ServiceInstance.service_type == ServiceType.SONARR
        )
        instance = session.exec(statement).first()
        
        if not instance:
            return HTMLResponse('''
                <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-800 text-sm">✗ Sonarr instance not found</p>
                </div>
            ''')
        
        # Extract form data
        form_data = await request.form()
        sonarr_name = form_data.get("sonarr_name", "").strip()
        sonarr_hostname = form_data.get("sonarr_hostname", "").strip()
        sonarr_port = form_data.get("sonarr_port", "8989").strip()
        sonarr_api_key = form_data.get("sonarr_api_key", "").strip()
        use_ssl = form_data.get("use_ssl") == "on"
        sonarr_base_url = form_data.get("sonarr_base_url", "").strip()
        
        # Validation
        if not sonarr_name or not sonarr_hostname or not sonarr_port or not sonarr_api_key:
            return HTMLResponse('''
                <div class="p-3 bg-red-50 border border-red-200 rounded-md mb-4">
                    <p class="text-red-800 text-sm">✗ Instance name, hostname, port, and API key are required</p>
                </div>
            ''')
        
        # Build URL from components
        protocol = "https" if use_ssl else "http"
        sonarr_url = f"{protocol}://{sonarr_hostname}:{sonarr_port}"
        
        # Update instance
        instance.name = sonarr_name
        instance.url = sonarr_url
        instance.api_key = sonarr_api_key
        
        # Update settings - extract all form data with correct field names
        quality_profile_id = form_data.get("sonarr_quality_profile_id", "").strip()
        root_folder_path = form_data.get("sonarr_root_folder_path", "").strip()
        language_profile_id = form_data.get("sonarr_language_profile_id", "1").strip()
        tags = form_data.get("tags", "").strip()
        external_url = form_data.get("external_url", "").strip()
        enable_scan = form_data.get("enable_scan") == "on"
        enable_automatic_search = form_data.get("enable_automatic_search") == "on"
        enable_integration = form_data.get("enable_integration") == "on"
        enable_season_folders = form_data.get("enable_season_folders") == "on"
        anime_standard_format = form_data.get("anime_standard_format") == "on"
        
        from ..models.service_instance import SONARR_DEFAULT_SETTINGS
        settings = SONARR_DEFAULT_SETTINGS.copy()
        settings.update({
            "hostname": sonarr_hostname,
            "port": int(sonarr_port),
            "use_ssl": use_ssl,
            "base_url": sonarr_base_url,
            "quality_profile_id": int(quality_profile_id) if quality_profile_id else None,
            "root_folder_path": root_folder_path if root_folder_path else None,
            "language_profile_id": int(language_profile_id) if language_profile_id else 1,
            "tags": [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else [],
            "external_url": external_url,
            "enable_scan": enable_scan,
            "enable_automatic_search": enable_automatic_search,
            "enable_integration": enable_integration,
            "season_folder": enable_season_folders,
            "anime_standard_format": anime_standard_format
        })
        instance.set_settings(settings)
        
        # Save to database
        session.add(instance)
        session.commit()
        
        # Get current base_url for HTML responses  
        current_base_url = SettingsService.get_base_url(session)
        
        # Close modal and refresh list
        return HTMLResponse(f'''
            <div class="p-3 bg-green-50 border border-green-200 rounded-md mb-4">
                <p class="text-green-800 text-sm font-medium">✓ Sonarr instance "{sonarr_name}" updated successfully!</p>
            </div>
            <script>
                // Close modal
                hideServiceModal();
                // Refresh the instances list
                htmx.ajax('GET', '{current_base_url}/admin/services/sonarr/list', {{
                    target: '#sonarr-instances',
                    swap: 'innerHTML'
                }});
            </script>
        ''')
        
    except Exception as e:
        logger.error(f"Error updating Sonarr instance: {e}")
        return HTMLResponse(f'''
            <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                <p class="text-red-800 text-sm">✗ Error updating instance: {str(e)}</p>
            </div>
        ''')


@router.patch("/services/sonarr/{instance_id}/update")
async def patch_sonarr_integration(
    instance_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Update Sonarr integration setting"""
    try:
        from sqlmodel import select
        from ..models.service_instance import ServiceInstance, ServiceType
        
        # Get the instance
        statement = select(ServiceInstance).where(
            ServiceInstance.id == instance_id,
            ServiceInstance.service_type == ServiceType.SONARR
        )
        instance = session.exec(statement).first()
        
        if not instance:
            return JSONResponse(
                status_code=404,
                content={"error": "Sonarr instance not found"}
            )
        
        # Parse JSON body
        body = await request.json()
        enable_integration = body.get('enable_integration', True)
        
        # Update settings
        settings = instance.get_settings()
        settings['enable_integration'] = enable_integration
        instance.set_settings(settings)
        
        # Save to database
        session.add(instance)
        session.commit()
        
        return JSONResponse({"success": True, "enable_integration": enable_integration})
        
    except Exception as e:
        print(f"Error updating Sonarr integration: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@router.get("/services/sonarr/add", response_class=HTMLResponse)
async def add_sonarr_form(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get Sonarr instance add form"""
    current_base_url = SettingsService.get_base_url(session)
    
    return HTMLResponse(f'''
        <div>
            <h4 class="text-lg font-medium text-gray-900 mb-4">Add Sonarr Instance</h4>
            <form hx-post="{current_base_url}/admin/services/sonarr/create" hx-target="#sonarr-instances" class="space-y-6">
                
                <!-- Basic Settings -->
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                        <label for="sonarr_name" class="block text-sm font-medium text-gray-700">Instance Name</label>
                        <input type="text" name="sonarr_name" id="sonarr_name" 
                               placeholder="e.g., Sonarr 4K, TV Shows HD"
                               class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                        <p class="mt-1 text-xs text-gray-500">Friendly name to identify this instance</p>
                    </div>
                    
                    <div class="flex items-center mt-6">
                        <input type="checkbox" name="is_default" id="is_default" 
                               class="h-4 w-4 text-purple-600 border-gray-300 rounded">
                        <label for="is_default" class="ml-2 text-sm text-gray-700">
                            Default instance for TV show requests
                        </label>
                    </div>
                </div>
                
                <!-- Connection Settings -->
                <div class="border-t pt-6">
                    <h5 class="text-md font-semibold text-gray-900 mb-4">Connection Settings</h5>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                            <label for="sonarr_hostname" class="block text-sm font-medium text-gray-700">Hostname/IP</label>
                            <input type="text" name="sonarr_hostname" id="sonarr_hostname" 
                                   placeholder="172.20.0.11 or localhost"
                                   class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                            <p class="mt-1 text-xs text-gray-500">Server hostname or IP address</p>
                        </div>
                        
                        <div>
                            <label for="sonarr_port" class="block text-sm font-medium text-gray-700">Port</label>
                            <input type="number" name="sonarr_port" id="sonarr_port" 
                                   value="8989"
                                   min="1" max="65535"
                                   class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                            <p class="mt-1 text-xs text-gray-500">Default: 8989</p>
                        </div>
                        
                        <div class="flex items-end">
                            <div class="flex items-center h-10">
                                <input type="checkbox" name="use_ssl" id="sonarr_use_ssl" 
                                       class="h-4 w-4 text-purple-600 border-gray-300 rounded">
                                <label for="sonarr_use_ssl" class="ml-2 text-sm text-gray-700">Use HTTPS</label>
                            </div>
                        </div>
                    </div>
                    
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                        
                        <div>
                            <label for="sonarr_api_key" class="block text-sm font-medium text-gray-700">API Key</label>
                            <input type="password" name="sonarr_api_key" id="sonarr_api_key" 
                                   placeholder="Your Sonarr API key"
                                   class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                            <p class="mt-1 text-xs text-gray-500">Found in Sonarr Settings → General → Security</p>
                        </div>
                        
                        <div>
                            <label for="sonarr_base_url" class="block text-sm font-medium text-gray-700">Base URL</label>
                            <input type="text" name="sonarr_base_url" id="sonarr_base_url" 
                                   placeholder="/sonarr (optional)"
                                   class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                            <p class="mt-1 text-xs text-gray-500">For reverse proxy setups</p>
                        </div>
                    </div>
                </div>
                
                <!-- Test Connection -->
                <div>
                    <button type="button" 
                            hx-post="{current_base_url}/admin/services/sonarr/test" 
                            hx-target="#sonarr-test-results"
                            hx-include="form"
                            class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-md text-sm font-medium">
                        <svg class="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                        Test Connection
                    </button>
                    <div id="sonarr-test-results" class="mt-4"></div>
                </div>
                
                <!-- Advanced Settings (Collapsed by default) -->
                <div class="border-t pt-4">
                    <button type="button" onclick="toggleSonarrAdvancedSettings()" 
                            class="flex items-center justify-between w-full text-left focus:outline-none">
                        <h5 class="text-md font-semibold text-gray-900">Advanced Settings</h5>
                        <svg id="sonarr-advanced-chevron" class="w-5 h-5 text-gray-500 transform transition-transform duration-200" 
                             fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                        </svg>
                    </button>
                    
                    <div id="sonarr-advanced-settings" class="hidden mt-4 space-y-4">
                        <!-- Default Settings -->
                <div class="border-t pt-6">
                    <h5 class="text-md font-medium text-gray-900 mb-4">Default Settings</h5>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div>
                            <label for="sonarr_quality_profile_id" class="block text-sm font-medium text-gray-700">Quality Profile</label>
                            <select name="sonarr_quality_profile_id" id="sonarr_quality_profile_id" 
                                    class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                                <option value="">Test connection to load profiles</option>
                            </select>
                        </div>
                        
                        <div>
                            <label for="sonarr_root_folder_path" class="block text-sm font-medium text-gray-700">Root Folder</label>
                            <select name="sonarr_root_folder_path" id="sonarr_root_folder_path" 
                                    class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                                <option value="">Test connection to load folders</option>
                            </select>
                        </div>
                        
                        <div>
                            <label for="sonarr_language_profile_id" class="block text-sm font-medium text-gray-700">Language Profile</label>
                            <select name="sonarr_language_profile_id" id="sonarr_language_profile_id" 
                                    class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                                <option value="">Test connection to load profiles</option>
                            </select>
                        </div>
                        
                        <div>
                            <label for="tags" class="block text-sm font-medium text-gray-700">Tags</label>
                            <input type="text" name="tags" id="tags" 
                                   placeholder="4k, uhd, anime (comma separated)"
                                   class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                            <p class="mt-1 text-xs text-gray-500">Optional tags to apply to requests</p>
                        </div>
                    </div>
                </div>
                
                <!-- Advanced Settings -->
                <div class="border-t pt-6">
                    <h5 class="text-md font-medium text-gray-900 mb-4">Advanced Settings</h5>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div class="flex items-center">
                            <input type="checkbox" name="enable_scan" id="enable_scan" checked
                                   class="h-4 w-4 text-purple-600 border-gray-300 rounded">
                            <label for="enable_scan" class="ml-2 text-sm text-gray-700">
                                Enable library scanning
                            </label>
                        </div>
                        
                        <div class="flex items-center">
                            <input type="checkbox" name="enable_automatic_search" id="enable_automatic_search" 
                                   checked
                                   class="h-4 w-4 text-purple-600 border-gray-300 rounded">
                            <label for="enable_automatic_search" class="ml-2 text-sm text-gray-700">
                                Enable automatic search on approval
                            </label>
                        </div>
                        
                        <div class="flex items-center">
                            <input type="checkbox" name="enable_integration" id="enable_integration" 
                                   checked
                                   class="h-4 w-4 text-purple-600 border-gray-300 rounded">
                            <label for="enable_integration" class="ml-2 text-sm text-gray-700">
                                Enable automatic integration (send approved requests to Sonarr)
                            </label>
                        </div>
                        
                        <div class="flex items-center">
                            <input type="checkbox" name="enable_season_folders" id="enable_season_folders" checked
                                   class="h-4 w-4 text-purple-600 border-gray-300 rounded">
                            <label for="enable_season_folders" class="ml-2 text-sm text-gray-700">
                                Enable season folders
                            </label>
                        </div>
                        
                        <div class="flex items-center">
                            <input type="checkbox" name="anime_standard_format" id="anime_standard_format"
                                   class="h-4 w-4 text-purple-600 border-gray-300 rounded">
                            <label for="anime_standard_format" class="ml-2 text-sm text-gray-700">
                                Use anime standard format
                            </label>
                        </div>
                    </div>
                    
                    <div class="mt-4">
                        <label for="external_url" class="block text-sm font-medium text-gray-700">External URL</label>
                        <input type="url" name="external_url" id="external_url" 
                               placeholder="https://sonarr.yourdomain.com (optional)"
                               class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-purple-500 focus:border-purple-500">
                        <p class="mt-1 text-xs text-gray-500">Public URL for external access</p>
                    </div>
                </div>
                
                <div class="flex justify-between pt-6 border-t">
                    <button type="button" 
                            hx-post="{current_base_url}/admin/services/sonarr/test" 
                            hx-target="#test-results"
                            hx-include="form"
                            class="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded-md text-sm font-medium">
                        Test Connection
                    </button>
                    <div class="space-x-3">
                        <button type="button" onclick="hideServiceModal()"
                                class="bg-gray-300 hover:bg-gray-400 text-gray-700 px-4 py-2 rounded-md text-sm font-medium">
                            Cancel
                        </button>
                        <button type="submit" 
                                class="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-md text-sm font-medium">
                            Save Sonarr Instance
                        </button>
                    </div>
                </div>
                
                <div id="test-results" class="mt-4"></div>
            </form>
        </div>
    ''')


@router.get("/tabs/jobs", response_class=HTMLResponse)
async def admin_jobs_tab(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get jobs tab content"""
    from ..services.background_jobs import background_jobs
    from ..services.plex_sync_service import PlexSyncService

    # Get job status
    all_jobs = background_jobs.get_all_jobs_status()
    
    # Get library sync stats
    sync_stats = None
    try:
        sync_service = PlexSyncService(session)
        sync_stats = sync_service.get_sync_stats()
    except Exception as e:
        print(f"Error getting sync stats: {e}")
        sync_stats = {'error': str(e)}
    
    # Format the jobs for display
    jobs_info = {}
    for job_name, job_data in all_jobs.items():
        jobs_info[job_name] = {
            'name': job_data.get('name', job_name.replace('_', ' ').title()),
            'description': job_data.get('description', ''),
            'interval': f"Every {job_data.get('interval_seconds', 3600) // 60} minutes",
            'last_run': job_data.get('last_run').strftime('%Y-%m-%d %H:%M:%S') if job_data.get('last_run') else 'Never',
            'next_run': job_data.get('next_run').strftime('%Y-%m-%d %H:%M:%S') if job_data.get('next_run') else 'Not scheduled',
            'running': job_data.get('running', False),
            'stats': job_data.get('stats', {}),
            'enabled': job_data.get('enabled', False),
            'interval_seconds': job_data.get('interval_seconds', 0)
        }
    
    # Get current scheduling configuration from the background jobs
    library_sync_job = all_jobs.get('library_sync', {})
    download_status_job = all_jobs.get('download_status_check', {})
    
    # Determine sync schedule based on job configuration
    sync_schedule = "disabled"
    if library_sync_job.get('enabled', False):
        interval = library_sync_job.get('interval_seconds', 3600)
        if interval <= 3600:  # 1 hour
            sync_schedule = "hourly"
        elif interval <= 14400:  # 4 hours
            sync_schedule = "4hours"
        elif interval <= 86400:  # 24 hours
            sync_schedule = "daily"
        else:
            sync_schedule = "weekly"
    
    # Format next sync time
    next_sync = library_sync_job.get('next_run')
    next_sync_formatted = next_sync.strftime('%Y-%m-%d %H:%M:%S UTC') if next_sync else "Not scheduled"
    
    # Determine download status check schedule
    download_schedule = "disabled"
    if download_status_job.get('enabled', False):
        interval = download_status_job.get('interval_seconds', 120)
        if interval <= 120:  # 2 minutes
            download_schedule = "2minutes"
        elif interval <= 300:  # 5 minutes
            download_schedule = "5minutes"
        elif interval <= 900:  # 15 minutes
            download_schedule = "15minutes"
        elif interval <= 1800:  # 30 minutes
            download_schedule = "30minutes"
        else:  # 1 hour or more
            download_schedule = "hourly"
    
    # Format next download check time
    next_download_check = download_status_job.get('next_run')
    next_download_check_formatted = next_download_check.strftime('%Y-%m-%d %H:%M:%S UTC') if next_download_check else "Not scheduled"
    
    return create_template_response("admin_tabs/jobs.html", {
        "request": request,
        "current_user": current_user,
        "jobs": jobs_info,
        "sync_stats": sync_stats,
        "sync_schedule": sync_schedule,
        "next_sync": next_sync_formatted,
        "download_schedule": download_schedule,
        "next_download_check": next_download_check_formatted,
        "cleanup_schedule": "disabled",  # Not implemented yet
        "cleanup_retention": "30days",  # Default value
        "job_stats": {
            "active": sum(1 for job in all_jobs.values() if job.get('running', False)),
            "scheduled": sum(1 for job in all_jobs.values() if job.get('enabled', False)),
            "failed": 0  # TODO: Track failed jobs
        }
    })


# Enhanced Services Endpoints

@router.post("/settings/update-services")
async def update_services_settings(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session),
    service: str = Form(...),
    
    # TMDB settings
    tmdb_api_key: Optional[str] = Form(None),
    tmdb_language: Optional[str] = Form(None),
    
    # Radarr settings
    radarr_url: Optional[str] = Form(None),
    radarr_api_key: Optional[str] = Form(None),
    radarr_quality_profile: Optional[str] = Form(None),
    radarr_root_folder: Optional[str] = Form(None),
    
    # Sonarr settings
    sonarr_url: Optional[str] = Form(None),
    sonarr_api_key: Optional[str] = Form(None),
    sonarr_quality_profile: Optional[str] = Form(None),
    sonarr_root_folder: Optional[str] = Form(None),
    sonarr_language_profile: Optional[str] = Form(None)
):
    """Update individual service settings"""
    try:
        settings_data = {}
        
        if service == "tmdb":
            if tmdb_api_key and tmdb_api_key != "•" * 20:
                settings_data['tmdb_api_key'] = tmdb_api_key.strip()
            # tmdb_language will be handled after database migration
                
        elif service == "radarr":
            if radarr_url:
                settings_data['radarr_url'] = radarr_url.strip()
            if radarr_api_key and radarr_api_key != "•" * 20:
                settings_data['radarr_api_key'] = radarr_api_key.strip()
            # Additional radarr fields will be handled after database migration
                
        elif service == "sonarr":
            if sonarr_url:
                settings_data['sonarr_url'] = sonarr_url.strip()
            if sonarr_api_key and sonarr_api_key != "•" * 20:
                settings_data['sonarr_api_key'] = sonarr_api_key.strip()
            # Additional sonarr fields will be handled after database migration
        
        # Update settings
        SettingsService.update_settings(session, settings_data, current_user.id)
        
        # Get current base_url for HTML responses
        current_base_url = SettingsService.get_base_url(session)
        
        # Return success message
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
                    <p class="ml-3 text-sm text-green-700">{service.upper()} settings updated successfully!</p>
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
                    <p class="ml-3 text-sm text-red-700">Failed to update {service} settings: {str(e)}</p>
                </div>
            </div>
        """)


@router.post("/services/test/{service}")
async def test_service_connection(
    service: str,
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Test connection to a specific service"""
    from fastapi.responses import HTMLResponse
    
    try:
        settings = SettingsService.get_settings(session)
        
        if service == "tmdb":
            if not settings.tmdb_api_key:
                return HTMLResponse(f"""
                    <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-md">
                        <div class="flex">
                            <svg class="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                            </svg>
                            <p class="ml-3 text-sm text-yellow-700">TMDB API key is required for testing connection.</p>
                        </div>
                    </div>
                """)
            
            # Test TMDB connection
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.themoviedb.org/3/configuration?api_key={settings.tmdb_api_key}"
                )
                
            if response.status_code == 200:
                return HTMLResponse(f"""
                    <div class="p-4 bg-green-50 border border-green-200 rounded-md">
                        <div class="flex">
                            <svg class="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                            </svg>
                            <p class="ml-3 text-sm text-green-700">TMDB connection successful!</p>
                        </div>
                    </div>
                """)
            else:
                return HTMLResponse(f"""
                    <div class="p-4 bg-red-50 border border-red-200 rounded-md">
                        <div class="flex">
                            <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                            </svg>
                            <p class="ml-3 text-sm text-red-700">TMDB connection failed: {response.status_code}</p>
                        </div>
                    </div>
                """)
                
        elif service == "radarr":
            if not settings.radarr_url or not settings.radarr_api_key:
                return HTMLResponse(f"""
                    <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-md">
                        <div class="flex">
                            <svg class="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                            </svg>
                            <p class="ml-3 text-sm text-yellow-700">Radarr URL and API key are required for testing connection.</p>
                        </div>
                    </div>
                """)
            
            # Test Radarr connection and load profiles/folders
            import httpx
            headers = {"X-Api-Key": settings.radarr_api_key}
            base_url = settings.radarr_url.rstrip('/')
            
            async with httpx.AsyncClient() as client:
                # Test system status
                status_response = await client.get(f"{base_url}/api/v3/system/status", headers=headers)
                
                if status_response.status_code == 200:
                    # Get quality profiles
                    profiles_response = await client.get(f"{base_url}/api/v3/qualityprofile", headers=headers)
                    root_folders_response = await client.get(f"{base_url}/api/v3/rootfolder", headers=headers)
                    
                    profiles = profiles_response.json() if profiles_response.status_code == 200 else []
                    root_folders = root_folders_response.json() if root_folders_response.status_code == 200 else []
                    
                    # Build options HTML
                    profile_options = "".join([f'<option value="{p["id"]}">{p["name"]}</option>' for p in profiles])
                    folder_options = "".join([f'<option value="{f["id"]}">{f["path"]}</option>' for f in root_folders])
                    
                    return HTMLResponse(f"""
                        <div class="p-4 bg-green-50 border border-green-200 rounded-md">
                            <div class="flex">
                                <svg class="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                                </svg>
                                <p class="ml-3 text-sm text-green-700">Radarr connection successful! Loaded {len(profiles)} quality profiles and {len(root_folders)} root folders.</p>
                            </div>
                        </div>
                        <script>
                            document.getElementById('radarr_quality_profile').innerHTML = '<option value="">Select Quality Profile</option>{profile_options}';
                            document.getElementById('radarr_root_folder').innerHTML = '<option value="">Select Root Folder</option>{folder_options}';
                        </script>
                    """)
                else:
                    return HTMLResponse(f"""
                        <div class="p-4 bg-red-50 border border-red-200 rounded-md">
                            <div class="flex">
                                <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                                </svg>
                                <p class="ml-3 text-sm text-red-700">Radarr connection failed: {status_response.status_code}</p>
                            </div>
                        </div>
                    """)
                    
        elif service == "sonarr":
            if not settings.sonarr_url or not settings.sonarr_api_key:
                return HTMLResponse(f"""
                    <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-md">
                        <div class="flex">
                            <svg class="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                            </svg>
                            <p class="ml-3 text-sm text-yellow-700">Sonarr URL and API key are required for testing connection.</p>
                        </div>
                    </div>
                """)
            
            # Test Sonarr connection and load profiles/folders
            import httpx
            headers = {"X-Api-Key": settings.sonarr_api_key}
            base_url = settings.sonarr_url.rstrip('/')
            
            async with httpx.AsyncClient() as client:
                # Test system status
                status_response = await client.get(f"{base_url}/api/v3/system/status", headers=headers)
                
                if status_response.status_code == 200:
                    # Get quality profiles, language profiles, and root folders
                    profiles_response = await client.get(f"{base_url}/api/v3/qualityprofile", headers=headers)
                    language_response = await client.get(f"{base_url}/api/v3/languageprofile", headers=headers)
                    root_folders_response = await client.get(f"{base_url}/api/v3/rootfolder", headers=headers)
                    
                    profiles = profiles_response.json() if profiles_response.status_code == 200 else []
                    languages = language_response.json() if language_response.status_code == 200 else []
                    root_folders = root_folders_response.json() if root_folders_response.status_code == 200 else []
                    
                    # Build options HTML
                    profile_options = "".join([f'<option value="{p["id"]}">{p["name"]}</option>' for p in profiles])
                    language_options = "".join([f'<option value="{l["id"]}">{l["name"]}</option>' for l in languages])
                    folder_options = "".join([f'<option value="{f["id"]}">{f["path"]}</option>' for f in root_folders])
                    
                    return HTMLResponse(f"""
                        <div class="p-4 bg-green-50 border border-green-200 rounded-md">
                            <div class="flex">
                                <svg class="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                                </svg>
                                <p class="ml-3 text-sm text-green-700">Sonarr connection successful! Loaded {len(profiles)} quality profiles, {len(languages)} language profiles, and {len(root_folders)} root folders.</p>
                            </div>
                        </div>
                        <script>
                            document.getElementById('sonarr_quality_profile').innerHTML = '<option value="">Select Quality Profile</option>{profile_options}';
                            document.getElementById('sonarr_language_profile').innerHTML = '<option value="">Select Language Profile</option>{language_options}';
                            document.getElementById('sonarr_root_folder').innerHTML = '<option value="">Select Root Folder</option>{folder_options}';
                        </script>
                    """)
                else:
                    return HTMLResponse(f"""
                        <div class="p-4 bg-red-50 border border-red-200 rounded-md">
                            <div class="flex">
                                <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                                </svg>
                                <p class="ml-3 text-sm text-red-700">Sonarr connection failed: {status_response.status_code}</p>
                            </div>
                        </div>
                    """)
        else:
            return HTMLResponse(f"""
                <div class="p-4 bg-red-50 border border-red-200 rounded-md">
                    <div class="flex">
                        <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                        </svg>
                        <p class="ml-3 text-sm text-red-700">Unknown service: {service}</p>
                    </div>
                </div>
            """)
            
    except Exception as e:
        return HTMLResponse(f"""
            <div class="p-4 bg-red-50 border border-red-200 rounded-md">
                <div class="flex">
                    <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                    </svg>
                    <p class="ml-3 text-sm text-red-700">Connection test failed: {str(e)}</p>
                </div>
            </div>
        """)


@router.post("/services/test-all")
async def test_all_services(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Test connections to all configured services"""
    from fastapi.responses import HTMLResponse
    
    try:
        settings = SettingsService.get_settings(session)
        results = []
        
        # Test TMDB
        if settings.tmdb_api_key:
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"https://api.themoviedb.org/3/configuration?api_key={settings.tmdb_api_key}"
                    )
                if response.status_code == 200:
                    results.append({"service": "TMDB", "status": "success", "message": "Connected"})
                else:
                    results.append({"service": "TMDB", "status": "error", "message": f"Failed ({response.status_code})"})
            except Exception as e:
                results.append({"service": "TMDB", "status": "error", "message": f"Error: {str(e)}"})
        else:
            results.append({"service": "TMDB", "status": "warning", "message": "Not configured"})
        
        # Test Radarr
        if settings.radarr_url and settings.radarr_api_key:
            try:
                import httpx
                headers = {"X-Api-Key": settings.radarr_api_key}
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{settings.radarr_url.rstrip('/')}/api/v3/system/status", headers=headers)
                if response.status_code == 200:
                    results.append({"service": "Radarr", "status": "success", "message": "Connected"})
                else:
                    results.append({"service": "Radarr", "status": "error", "message": f"Failed ({response.status_code})"})
            except Exception as e:
                results.append({"service": "Radarr", "status": "error", "message": f"Error: {str(e)}"})
        else:
            results.append({"service": "Radarr", "status": "warning", "message": "Not configured"})
        
        # Test Sonarr
        if settings.sonarr_url and settings.sonarr_api_key:
            try:
                import httpx
                headers = {"X-Api-Key": settings.sonarr_api_key}
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{settings.sonarr_url.rstrip('/')}/api/v3/system/status", headers=headers)
                if response.status_code == 200:
                    results.append({"service": "Sonarr", "status": "success", "message": "Connected"})
                else:
                    results.append({"service": "Sonarr", "status": "error", "message": f"Failed ({response.status_code})"})
            except Exception as e:
                results.append({"service": "Sonarr", "status": "error", "message": f"Error: {str(e)}"})
        else:
            results.append({"service": "Sonarr", "status": "warning", "message": "Not configured"})
        
        # Build results HTML
        result_items = []
        for result in results:
            status_color = {
                "success": "green",
                "error": "red", 
                "warning": "yellow"
            }.get(result["status"], "gray")
            
            status_icon = {
                "success": "M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z",
                "error": "M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z",
                "warning": "M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
            }.get(result["status"], "")
            
            result_items.append(f"""
                <div class="flex items-center justify-between p-3 bg-{status_color}-50 border border-{status_color}-200 rounded-md">
                    <div class="flex items-center">
                        <svg class="w-5 h-5 text-{status_color}-400" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="{status_icon}" clip-rule="evenodd"></path>
                        </svg>
                        <span class="ml-3 text-sm font-medium text-{status_color}-800">{result["service"]}</span>
                    </div>
                    <span class="text-sm text-{status_color}-600">{result["message"]}</span>
                </div>
            """)
        
        return HTMLResponse(f"""
            <div class="space-y-3">
                <h4 class="text-md font-medium text-gray-900 mb-3">Service Health Results</h4>
                {"".join(result_items)}
            </div>
        """)
        
    except Exception as e:
        return HTMLResponse(f"""
            <div class="p-4 bg-red-50 border border-red-200 rounded-md">
                <div class="flex">
                    <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                    </svg>
                    <p class="ml-3 text-sm text-red-700">Health check failed: {str(e)}</p>
                </div>
            </div>
        """)


# Enhanced Jobs Endpoints

@router.post("/jobs/run/{job_type}")
async def run_manual_job(
    job_type: str,
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Run a manual job"""
    from fastapi.responses import HTMLResponse
    from ..services.background_jobs import background_jobs
    
    try:
        if job_type == "sync-library":
            result = await background_jobs.trigger_library_sync()
            
            if result['success']:
                return HTMLResponse(f"""
                    <div class="p-4 bg-green-50 border border-green-200 rounded-md">
                        <div class="flex">
                            <svg class="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                            </svg>
                            <p class="ml-3 text-sm text-green-700">Library sync started successfully!</p>
                        </div>
                    </div>
                """)
            else:
                return HTMLResponse(f"""
                    <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-md">
                        <div class="flex">
                            <svg class="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                            </svg>
                            <p class="ml-3 text-sm text-yellow-700">{result['message']}</p>
                        </div>
                    </div>
                """)
                
        elif job_type == "download-status":
            result = await background_jobs.trigger_download_status_check()
            
            if result['success']:
                return HTMLResponse(f"""
                    <div class="p-4 bg-green-50 border border-green-200 rounded-md">
                        <div class="flex">
                            <svg class="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                            </svg>
                            <p class="ml-3 text-sm text-green-700">Download status check started successfully!</p>
                        </div>
                    </div>
                """)
            else:
                return HTMLResponse(f"""
                    <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-md">
                        <div class="flex">
                            <svg class="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                            </svg>
                            <p class="ml-3 text-sm text-yellow-700">{result['message']}</p>
                        </div>
                    </div>
                """)
                
        elif job_type == "cleanup-requests":
            # Placeholder for request cleanup job
            return HTMLResponse(f"""
                <div class="p-4 bg-blue-50 border border-blue-200 rounded-md">
                    <div class="flex">
                        <svg class="w-5 h-5 text-blue-400" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path>
                        </svg>
                        <p class="ml-3 text-sm text-blue-700">Request cleanup functionality coming soon!</p>
                    </div>
                </div>
            """)
            
        elif job_type == "update-metadata":
            # Placeholder for metadata update job
            return HTMLResponse(f"""
                <div class="p-4 bg-blue-50 border border-blue-200 rounded-md">
                    <div class="flex">
                        <svg class="w-5 h-5 text-blue-400" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path>
                        </svg>
                        <p class="ml-3 text-sm text-blue-700">Metadata update functionality coming soon!</p>
                    </div>
                </div>
            """)
            
        elif job_type == "health-check":
            # Use the existing test-all services functionality
            return await test_all_services(request, current_user, session)
            
        else:
            return HTMLResponse(f"""
                <div class="p-4 bg-red-50 border border-red-200 rounded-md">
                    <div class="flex">
                        <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                        </svg>
                        <p class="ml-3 text-sm text-red-700">Unknown job type: {job_type}</p>
                    </div>
                </div>
            """)
            
    except Exception as e:
        return HTMLResponse(f"""
            <div class="p-4 bg-red-50 border border-red-200 rounded-md">
                <div class="flex">
                    <svg class="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                    </svg>
                    <p class="ml-3 text-sm text-red-700">Job execution failed: {str(e)}</p>
                </div>
            </div>
        """)


@router.get("/jobs/history")
async def get_job_history(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get job execution history"""
    from fastapi.responses import HTMLResponse
    from ..services.background_jobs import background_jobs
    
    # Get recent job execution history
    history = background_jobs.get_job_execution_history(limit=50)
    
    # Build history HTML
    if not history:
        return HTMLResponse("""
            <div class="text-center py-12">
                <svg class="w-12 h-12 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012-2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"></path>
                </svg>
                <h3 class="text-lg font-medium text-gray-900 mb-2">No Job History</h3>
                <p class="text-gray-500">Job execution history will appear here once jobs start running.</p>
            </div>
        """)
    
    history_items = []
    for execution in history:
        # Format timestamps
        started_at = execution['started_at'].strftime('%Y-%m-%d %H:%M:%S') if execution['started_at'] else "Unknown"
        completed_at = execution['completed_at'].strftime('%Y-%m-%d %H:%M:%S') if execution['completed_at'] else "Still running"
        
        # Determine status styling
        status = execution['status']
        if status == 'success':
            status_color = "green"
            status_bg = "bg-green-100"
            status_text_color = "text-green-800"
            status_icon = "✅"
        elif status == 'failed':
            status_color = "red"
            status_bg = "bg-red-100"
            status_text_color = "text-red-800"
            status_icon = "❌"
        else:  # running
            status_color = "blue"
            status_bg = "bg-blue-100"
            status_text_color = "text-blue-800"
            status_icon = "🔄"
        
        # Format duration
        duration_text = f"{execution['duration_seconds']:.1f}s" if execution['duration_seconds'] else "N/A"
        
        # Format triggered by
        triggered_by = execution['triggered_by'].capitalize()
        triggered_color = "text-blue-600" if execution['triggered_by'] == 'scheduler' else "text-gray-600"
        
        # Format job name
        job_display_name = {
            'library_sync': 'Library Sync',
            'download_status_check': 'Download Status Check'
        }.get(execution['job_name'], execution['job_name'].replace('_', ' ').title())
        
        history_items.append(f"""
            <tr class="hover:bg-gray-50">
                <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    {job_display_name}
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                    <span class="inline-flex items-center px-2 py-1 text-xs font-semibold rounded-full {status_bg} {status_text_color}">
                        {status_icon} {status.title()}
                    </span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {started_at}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {completed_at}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {duration_text}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm {triggered_color}">
                    {triggered_by}
                </td>
            </tr>
        """)
    
    else:
        history_content = "".join(history_items)
    
    return HTMLResponse(f"""
        <div class="overflow-hidden">
            <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                    <tr>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Job Name</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Started</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Completed</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Duration</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Triggered By</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-200">
                    {history_content}
                </tbody>
            </table>
        </div>
    """)




@router.post("/jobs/update-cleanup")
async def update_cleanup_settings(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Update cleanup job settings (placeholder)"""
    from fastapi.responses import HTMLResponse
    
    return HTMLResponse(f"""
        <div class="p-4 bg-blue-50 border border-blue-200 rounded-md">
            <div class="flex">
                <svg class="w-5 h-5 text-blue-400" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path>
                </svg>
                <p class="ml-3 text-sm text-blue-700">Cleanup settings configuration coming soon!</p>
            </div>
        </div>
    """)


@router.post("/jobs/update-schedule")
async def update_job_schedule(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    job_name: str = Form(...),
    interval: str = Form(...),
    enabled: bool = Form(default=True)
):
    """Update job scheduling configuration"""
    try:
        from ..services.background_jobs import background_jobs
        
        # Convert interval string to seconds
        interval_seconds = None
        if interval == "disabled":
            enabled = False
        elif interval == "2minutes":
            interval_seconds = 120
        elif interval == "5minutes":
            interval_seconds = 300
        elif interval == "15minutes":
            interval_seconds = 900
        elif interval == "30minutes":
            interval_seconds = 1800
        elif interval == "hourly":
            interval_seconds = 3600
        elif interval == "4hours":
            interval_seconds = 14400
        elif interval == "daily":
            interval_seconds = 86400
        elif interval == "weekly":
            interval_seconds = 604800
        else:
            raise ValueError(f"Unknown interval: {interval}")
        
        # Update the job schedule
        success = background_jobs.update_job_schedule(
            job_name=job_name,
            interval_seconds=interval_seconds,
            enabled=enabled
        )
        
        if success:
            if request.headers.get("HX-Request"):
                return HTMLResponse(f'''
                    <div class="p-3 bg-green-50 border border-green-200 rounded-md">
                        <p class="text-green-700 text-sm">✓ Job schedule updated successfully</p>
                    </div>
                ''')
            else:
                return {"success": True, "message": "Job schedule updated successfully"}
        else:
            if request.headers.get("HX-Request"):
                return HTMLResponse(f'''
                    <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                        <p class="text-red-700 text-sm">✗ Failed to update job schedule</p>
                    </div>
                ''')
            else:
                return {"success": False, "message": "Failed to update job schedule"}
                
    except Exception as e:
        print(f"Error updating job schedule: {e}")
        if request.headers.get("HX-Request"):
            return HTMLResponse(f'''
                <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-700 text-sm">✗ Error: {str(e)}</p>
                </div>
            ''')
        else:
            return {"success": False, "message": f"Error: {str(e)}"}


@router.post("/jobs/start-scheduler")
async def start_scheduler(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible)
):
    """Start or restart the background job scheduler"""
    try:
        from ..services.background_jobs import background_jobs
        
        # Stop and restart the scheduler to ensure clean state
        if background_jobs.running:
            background_jobs.stop()
        
        background_jobs.start()
        
        if request.headers.get("HX-Request"):
            return HTMLResponse(f'''
                <div class="p-3 bg-green-50 border border-green-200 rounded-md">
                    <p class="text-green-700 text-sm">✓ Background job scheduler started successfully</p>
                </div>
            ''')
        else:
            return {"success": True, "message": "Scheduler started successfully"}
            
    except Exception as e:
        print(f"Error starting scheduler: {e}")
        if request.headers.get("HX-Request"):
            return HTMLResponse(f'''
                <div class="p-3 bg-red-50 border border-red-200 rounded-md">
                    <p class="text-red-700 text-sm">✗ Error starting scheduler: {str(e)}</p>
                </div>
            ''')
        else:
            return {"success": False, "message": f"Error: {str(e)}"}

