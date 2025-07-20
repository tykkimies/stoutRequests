"""
Permission decorators for enforcing granular role-based access control
"""

from functools import wraps
from fastapi import HTTPException, Depends
from sqlmodel import Session
from typing import Union, List, Callable, Any

from ..models.user import User
from ..models.role import PermissionFlags
from ..services.permissions_service import PermissionsService
from ..core.database import get_session
from ..api.auth import get_current_user_flexible


def require_permission(permission: Union[str, List[str]], allow_admin_override: bool = True):
    """
    Decorator that requires specific permission(s) to access an endpoint.
    
    Args:
        permission: Single permission string or list of permissions (ANY match)
        allow_admin_override: If True, full admins can access regardless of specific permission
    
    Usage:
        @require_permission(PermissionFlags.ADMIN_APPROVE_REQUESTS)
        async def approve_request(...):
            pass
            
        @require_permission([PermissionFlags.REQUEST_MOVIES, PermissionFlags.REQUEST_TV])
        async def create_request(...):
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user and session from kwargs or dependencies
            current_user = kwargs.get('current_user')
            session = kwargs.get('session')
            
            if not current_user or not session:
                raise HTTPException(status_code=401, detail="Authentication required")
            
            permissions_service = PermissionsService(session)
            
            # Check if user is admin with override capability
            if allow_admin_override:
                from ..core.permissions import is_user_admin
                if is_user_admin(current_user, session):
                    return await func(*args, **kwargs)
            
            # Check specific permissions
            permissions_to_check = permission if isinstance(permission, list) else [permission]
            
            for perm in permissions_to_check:
                if permissions_service.has_permission(current_user.id, perm):
                    return await func(*args, **kwargs)
            
            # No matching permissions found
            perm_names = ", ".join(permissions_to_check)
            raise HTTPException(
                status_code=403, 
                detail=f"Insufficient permissions. Required: {perm_names}"
            )
            
        return wrapper
    return decorator


def require_any_permission(*permissions: str, allow_admin_override: bool = True):
    """
    Decorator that requires ANY of the specified permissions.
    More readable than using require_permission with a list.
    
    Usage:
        @require_any_permission(
            PermissionFlags.ADMIN_APPROVE_REQUESTS,
            PermissionFlags.REQUEST_AUTO_APPROVE_MOVIES
        )
        async def approve_movie_request(...):
            pass
    """
    return require_permission(list(permissions), allow_admin_override)


def require_all_permissions(*permissions: str, allow_admin_override: bool = True):
    """
    Decorator that requires ALL of the specified permissions.
    
    Usage:
        @require_all_permissions(
            PermissionFlags.ADMIN_MANAGE_USERS,
            PermissionFlags.ADMIN_MANAGE_ROLES
        )
        async def assign_user_role(...):
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            session = kwargs.get('session')
            
            if not current_user or not session:
                raise HTTPException(status_code=401, detail="Authentication required")
            
            permissions_service = PermissionsService(session)
            
            # Check if user is admin with override capability
            if allow_admin_override:
                from ..core.permissions import is_user_admin
                if is_user_admin(current_user, session):
                    return await func(*args, **kwargs)
            
            # Check that user has ALL required permissions
            missing_permissions = []
            for perm in permissions:
                if not permissions_service.has_permission(current_user.id, perm):
                    missing_permissions.append(perm)
            
            if missing_permissions:
                perm_names = ", ".join(missing_permissions)
                raise HTTPException(
                    status_code=403, 
                    detail=f"Missing required permissions: {perm_names}"
                )
            
            return await func(*args, **kwargs)
            
        return wrapper
    return decorator


def require_self_or_permission(permission: str, user_id_param: str = "user_id"):
    """
    Decorator that allows access if the user is accessing their own data
    OR has the specified permission.
    
    Args:
        permission: Permission required for accessing other users' data
        user_id_param: Name of the parameter containing the target user ID
    
    Usage:
        @require_self_or_permission(PermissionFlags.ADMIN_MANAGE_USERS, "target_user_id")
        async def get_user_profile(target_user_id: int, current_user: User, ...):
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            session = kwargs.get('session')
            target_user_id = kwargs.get(user_id_param)
            
            if not current_user or not session:
                raise HTTPException(status_code=401, detail="Authentication required")
            
            # Allow if user is accessing their own data
            if current_user.id == target_user_id:
                return await func(*args, **kwargs)
            
            # Check if user has permission to access other users' data
            permissions_service = PermissionsService(session)
            
            # Admin override
            from ..core.permissions import is_user_admin
            if is_user_admin(current_user, session):
                return await func(*args, **kwargs)
            
            # Check specific permission
            if permissions_service.has_permission(current_user.id, permission):
                return await func(*args, **kwargs)
            
            raise HTTPException(
                status_code=403, 
                detail="Insufficient permissions to access other users' data"
            )
            
        return wrapper
    return decorator


def check_request_permissions(current_user: User, session: Session, media_type: str = None) -> dict:
    """
    Helper function to check what request permissions a user has.
    Returns a dict of capabilities for use in templates and logic.
    
    Args:
        current_user: The user to check permissions for
        session: Database session
        media_type: Optional media type to check specific permissions for
    
    Returns:
        dict: Dictionary of permission flags
    """
    permissions_service = PermissionsService(session)
    user_id = current_user.id
    
    # Check if user is admin (gets all permissions)
    from ..core.permissions import is_user_admin
    is_admin = is_user_admin(current_user, session)
    
    if is_admin:
        # Admins get all permissions
        return {
            'can_request_movies': True,
            'can_request_tv': True,
            'can_request_4k': True,
            'can_auto_approve': True,
            'can_view_all_requests': True,
            'can_approve_requests': True,
            'can_delete_requests': True,
            'can_manage_users': True,
            'can_manage_settings': True,
            'is_admin': True,
            'request_limit_override': True
        }
    
    return {
        'can_request_movies': permissions_service.has_permission(user_id, PermissionFlags.REQUEST_MOVIES),
        'can_request_tv': permissions_service.has_permission(user_id, PermissionFlags.REQUEST_TV),
        'can_request_4k': permissions_service.has_permission(user_id, PermissionFlags.REQUEST_4K),
        'can_auto_approve': (
            permissions_service.has_permission(user_id, PermissionFlags.REQUEST_AUTO_APPROVE_MOVIES) or
            permissions_service.has_permission(user_id, PermissionFlags.REQUEST_AUTO_APPROVE_TV) or
            permissions_service.has_permission(user_id, PermissionFlags.REQUEST_AUTO_APPROVE_4K)
        ),
        'can_view_all_requests': permissions_service.has_permission(user_id, PermissionFlags.REQUEST_VIEW_ALL),
        'can_approve_requests': permissions_service.has_permission(user_id, PermissionFlags.ADMIN_APPROVE_REQUESTS),
        'can_delete_requests': permissions_service.has_permission(user_id, PermissionFlags.ADMIN_DELETE_REQUESTS),
        'can_manage_users': permissions_service.has_permission(user_id, PermissionFlags.ADMIN_MANAGE_USERS),
        'can_manage_settings': permissions_service.has_permission(user_id, PermissionFlags.ADMIN_MANAGE_SETTINGS),
        'is_admin': False,
        'request_limit_override': permissions_service.has_permission(user_id, PermissionFlags.REQUEST_UNLIMITED)
    }


def check_media_type_permission(current_user: User, session: Session, media_type: str) -> bool:
    """
    Check if user can request a specific media type.
    
    Args:
        current_user: User to check
        session: Database session  
        media_type: 'movie' or 'tv'
    
    Returns:
        bool: True if user can request this media type
    """
    permissions_service = PermissionsService(session)
    
    # Admin override
    from ..core.permissions import is_user_admin
    if is_user_admin(current_user, session):
        return True
    
    if media_type == 'movie':
        return permissions_service.has_permission(current_user.id, PermissionFlags.REQUEST_MOVIES)
    elif media_type == 'tv':
        return permissions_service.has_permission(current_user.id, PermissionFlags.REQUEST_TV)
    
    return False