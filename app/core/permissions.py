"""
Core permission checking utilities for consistent role-based access control
"""

from sqlmodel import Session, select
from typing import Optional
from ..models.user import User


def is_user_admin(user: Optional[User], session: Session) -> bool:
    """
    Check if a user has admin permissions using the new role-based system
    with fallback to legacy is_admin field.
    
    Args:
        user: User object to check (can be None)
        session: Database session
        
    Returns:
        bool: True if user has admin permissions, False otherwise
    """
    if not user:
        return False
    
    # Server owners are always admin (unchangeable)
    if getattr(user, 'is_server_owner', False):
        return True
    
    try:
        from ..services.permissions_service import PermissionsService
        permissions_service = PermissionsService(session)
        user_role = permissions_service.get_user_role(user.id)
        
        # Check if user has admin role in new system
        if user_role and 'admin' in user_role.name.lower():
            return True
        
        # Fallback to legacy admin check if no role assigned
        if not user_role and user.is_admin:
            return True
            
        return False
        
    except Exception as e:
        print(f"Error checking admin permissions for user {user.id}: {e}")
        # Fallback to legacy check on error
        return getattr(user, 'is_admin', False)


def get_user_display_info(user: User, session: Session) -> dict:
    """
    Get display information for a user including their role.
    
    Args:
        user: User object
        session: Database session
        
    Returns:
        dict: Display info with role_text, role_color, is_admin
    """
    # Server owners get special treatment
    if getattr(user, 'is_server_owner', False):
        return {
            "role_text": "Server Owner",
            "role_color": "red",  # Special color for server owner
            "is_admin": True,
            "has_role": True,
            "is_server_owner": True
        }
    
    try:
        from ..services.permissions_service import PermissionsService
        permissions_service = PermissionsService(session)
        user_role = permissions_service.get_user_role(user.id)
        
        if user_role:
            role_text = user_role.display_name
            # Color based on role
            if 'admin' in user_role.name.lower():
                role_color = "yellow"
            elif 'moderator' in user_role.name.lower():
                role_color = "purple"
            else:
                role_color = "blue"
            is_admin = 'admin' in user_role.name.lower()
        else:
            # Fallback to legacy system if no role assigned
            role_color = "yellow" if user.is_admin else "blue"
            role_text = "Legacy Admin" if user.is_admin else "Basic User"
            is_admin = user.is_admin
            
        return {
            "role_text": role_text,
            "role_color": role_color,
            "is_admin": is_admin,
            "has_role": user_role is not None,
            "is_server_owner": False
        }
        
    except Exception as e:
        print(f"Error getting user display info for user {user.id}: {e}")
        # Fallback to legacy on error
        return {
            "role_text": "Legacy Admin" if user.is_admin else "Basic User",
            "role_color": "yellow" if user.is_admin else "blue",
            "is_admin": user.is_admin,
            "has_role": False,
            "is_server_owner": False
        }


def ensure_first_admin_has_role(session: Session) -> None:
    """
    Ensure the first admin user has an Administrator role assigned.
    This handles the migration from legacy is_admin to role-based system.
    """
    try:
        from ..services.permissions_service import PermissionsService
        from ..models.role import Role
        
        permissions_service = PermissionsService(session)
        
        # Find the first admin user (typically the server owner)
        admin_statement = select(User).where(User.is_admin == True)
        first_admin = session.exec(admin_statement).first()
        
        if not first_admin:
            return  # No admin users exist
        
        # Mark the first admin as server owner if not already marked
        if not getattr(first_admin, 'is_server_owner', False):
            first_admin.is_server_owner = True
            session.add(first_admin)
            session.commit()
            session.refresh(first_admin)
            print(f"✅ Marked first admin as server owner: {first_admin.username}")
        
        # Check if they already have a role
        existing_role = permissions_service.get_user_role(first_admin.id)
        if existing_role:
            return  # Already has a role
        
        # Find or create Administrator role
        admin_role_statement = select(Role).where(Role.name == "administrator")
        admin_role = session.exec(admin_role_statement).first()
        
        if not admin_role:
            # Create Administrator role if it doesn't exist
            from ..models.role import PermissionFlags
            admin_permissions = {
                "can_approve_requests": True,
                "can_manage_users": True,
                "can_view_all_requests": True,
                "can_manage_settings": True,
                "can_request_movies": True,
                "can_request_tv": True,
                "can_request_4k": True,
                "auto_approve_requests": True
            }
            
            admin_role = Role(
                name="administrator",
                display_name="Administrator",
                description="Full system access with all permissions",
                permissions=admin_permissions,
                is_default=False
            )
            session.add(admin_role)
            session.commit()
            session.refresh(admin_role)
        
        # Assign the role to the first admin
        permissions_service.assign_role_to_user(first_admin.id, admin_role.id)
        print(f"✅ Auto-assigned Administrator role to first admin user: {first_admin.username}")
        
    except Exception as e:
        print(f"Error ensuring first admin has role: {e}")
        # Don't raise - this should not break the app