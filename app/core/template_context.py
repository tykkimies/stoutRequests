"""
Global template context processor for Stout Requests
"""

from sqlmodel import Session
from .database import get_session, Session as SQLSession, engine
from ..services.settings_service import SettingsService


def url_for(path: str, base_url: str = "") -> str:
    """Construct a URL with the configured base URL"""
    if not path:
        return base_url or "/"
    
    # Ensure path starts with /
    if not path.startswith('/'):
        path = '/' + path
    
    # Combine base URL and path
    if base_url:
        # Remove trailing slash from base_url and leading slash from path to avoid double slashes
        result = base_url.rstrip('/') + path
    else:
        result = path
    
    return result


def get_global_template_context(current_user=None, request=None) -> dict:
    """Get global template context that should be available to all templates"""
    try:
        with SQLSession(engine) as session:
            settings = SettingsService.get_settings(session)
            
            # Handle base_url configuration - extract path only if full URL is provided
            original_base_url = settings.base_url
            base_url = settings.base_url.rstrip('/') if settings.base_url else ''
            
            print(f"🔍 Template Context: Original base_url from settings: '{original_base_url}'")
            
            # Fix for HTTPS/HTTP mixed content: if base_url contains protocol, extract path only
            if base_url and ('://' in base_url):
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(base_url)
                    base_url = parsed.path.rstrip('/')
                    print(f"🔧 Fixed base_url from full URL to path: {original_base_url} -> {base_url}")
                except Exception as e:
                    print(f"⚠️ Error parsing base_url {base_url}: {e}")
                    # Fallback: try to extract everything after the domain
                    if '://' in base_url:
                        try:
                            # Extract path from URL like "http://domain.com/path" -> "/path"
                            parts = base_url.split('/', 3)
                            base_url = '/' + parts[3] if len(parts) > 3 and parts[3] else ''
                            print(f"🔧 Fallback extraction: {original_base_url} -> {base_url}")
                        except:
                            base_url = ''
                            print(f"🔧 Fallback failed, clearing base_url")
            
            # Ensure base_url is clean and doesn't cause mixed content issues
            if base_url and not base_url.startswith('/'):
                base_url = '/' + base_url
            
            # Remove any remaining protocols that might have slipped through
            if '://' in base_url:
                print(f"⚠️ Still contains protocol, clearing: {base_url}")
                base_url = ''
            
            print(f"✅ Final base_url for templates: '{base_url}'")
            
            # Create a URL helper function that uses the corrected base URL
            def url_for_with_base(path: str) -> str:
                return url_for(path, base_url)
            
            # Add admin status and permissions if user is provided
            user_is_admin = False
            user_permissions = {}
            if current_user:
                try:
                    from ..core.permissions import is_user_admin
                    from ..core.permission_decorators import check_request_permissions
                    from ..services.permissions_service import PermissionsService
                    from ..models.role import PermissionFlags
                    
                    user_is_admin = is_user_admin(current_user, session)
                    user_permissions = check_request_permissions(current_user, session)
                    
                    # Add specific permission checks for templates
                    permissions_service = PermissionsService(session)
                    # Get user's custom permissions for additional checks
                    user_perms_obj = permissions_service.get_user_permissions(current_user.id)
                    custom_perms = user_perms_obj.get_custom_permissions() if user_perms_obj else {}
                    
                    user_permissions.update({
                        'can_approve_requests': permissions_service.has_permission(current_user.id, PermissionFlags.ADMIN_APPROVE_REQUESTS),
                        'can_manage_settings': permissions_service.has_permission(current_user.id, PermissionFlags.ADMIN_MANAGE_SETTINGS),
                        'can_manage_users': permissions_service.has_permission(current_user.id, PermissionFlags.ADMIN_MANAGE_USERS),
                        'can_view_all_requests': permissions_service.has_permission(current_user.id, PermissionFlags.REQUEST_VIEW_ALL),
                        'can_manage_all_requests': permissions_service.has_permission(current_user.id, PermissionFlags.REQUEST_MANAGE_ALL),
                        'can_library_sync': permissions_service.has_permission(current_user.id, PermissionFlags.ADMIN_LIBRARY_SYNC),
                        'can_request_movies': permissions_service.has_permission(current_user.id, PermissionFlags.REQUEST_MOVIES),
                        'can_request_tv': permissions_service.has_permission(current_user.id, PermissionFlags.REQUEST_TV),
                        # Custom permissions - admins get all permissions, others check custom_permissions
                        'can_view_other_users_requests': user_is_admin or custom_perms.get('can_view_other_users_requests', False),
                        'can_see_requester_username': user_is_admin or custom_perms.get('can_see_requester_username', False),
                    })
                    
                except Exception as e:
                    print(f"Error checking permissions in template context: {e}")
                    user_is_admin = getattr(current_user, 'is_admin', False)
                    user_permissions = {'is_admin': user_is_admin}
            
            result = {
                "site_theme": settings.site_theme,
                "app_name": settings.app_name,
                "base_url": base_url,
                "url_for": url_for_with_base,
                "user_is_admin": user_is_admin,
                "user_permissions": user_permissions
            }
            return result
    except Exception as e:
        print(f"Error getting global template context: {e}")
        # Fallback URL helper for error cases
        def fallback_url_for(path: str) -> str:
            return url_for(path, "")
        
        return {
            "site_theme": "default",
            "app_name": "Stout Requests",
            "base_url": "",
            "url_for": fallback_url_for,
            "user_is_admin": False,
            "user_permissions": {}
        }