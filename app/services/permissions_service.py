from sqlmodel import Session, select
from typing import Optional, Dict, List, Union
from datetime import datetime

from ..models.user import User
from ..models.role import Role, PermissionFlags
from ..models.user_permissions import UserPermissions
from ..models.media_request import MediaRequest, RequestStatus


class PermissionsService:
    """Service for managing user permissions and role-based access control"""
    
    def __init__(self, session: Session):
        self.session = session
    
    @classmethod
    def ensure_default_roles(cls, session: Session) -> None:
        """Create default system roles if they don't exist"""
        default_roles = [
            {
                'name': 'admin',
                'display_name': 'Administrator',
                'description': 'Full administrative access to all features',
                'permissions': PermissionFlags.get_admin_permissions(),
                'is_system': True,
                'is_default': False
            },
            {
                'name': 'moderator',
                'display_name': 'Moderator',
                'description': 'Can manage requests and moderate content with limited admin access',
                'permissions': PermissionFlags.get_moderator_permissions(),
                'is_system': True,
                'is_default': False
            },
            {
                'name': 'power_user',
                'display_name': 'Power User',
                'description': 'Advanced user with auto-approval and 4K access',
                'permissions': PermissionFlags.get_power_user_permissions(),
                'is_system': True,
                'is_default': False
            },
            {
                'name': 'basic_user',
                'display_name': 'Basic User',
                'description': 'Standard user with basic request privileges',
                'permissions': PermissionFlags.get_basic_user_permissions(),
                'is_system': True,
                'is_default': True
            },
            {
                'name': 'limited',
                'display_name': 'Limited User',
                'description': 'Restricted user with minimal permissions',
                'permissions': [PermissionFlags.ACCOUNT_EDIT_PROFILE, PermissionFlags.ACCOUNT_VIEW_ACTIVITY, PermissionFlags.DISCOVER_BROWSE],
                'is_system': True,
                'is_default': False
            }
        ]
        
        for role_data in default_roles:
            # Check if role exists
            statement = select(Role).where(Role.name == role_data['name'])
            existing_role = session.exec(statement).first()
            
            if not existing_role:
                # Create new role
                permissions_dict = {perm: True for perm in role_data['permissions']}
                role = Role(
                    name=role_data['name'],
                    display_name=role_data['display_name'],
                    description=role_data['description'],
                    is_system=role_data['is_system'],
                    is_default=role_data['is_default']
                )
                role.set_permissions(permissions_dict)
                session.add(role)
        
        session.commit()
    
    def get_user_permissions(self, user_id: int) -> Optional[UserPermissions]:
        """Get user permissions, creating default if not exists"""
        statement = select(UserPermissions).where(UserPermissions.user_id == user_id)
        user_perms = self.session.exec(statement).first()
        
        if not user_perms:
            # Create default permissions for user
            user_perms = self.create_default_user_permissions(user_id)
        
        return user_perms
    
    def get_user_role(self, user_id: int) -> Optional[Role]:
        """Get user's role"""
        user_perms = self.get_user_permissions(user_id)
        if not user_perms or not user_perms.role_id:
            return self.get_default_role()
        
        statement = select(Role).where(Role.id == user_perms.role_id)
        return self.session.exec(statement).first()
    
    def get_default_role(self) -> Optional[Role]:
        """Get the default role for new users"""
        statement = select(Role).where(Role.is_default == True)
        return self.session.exec(statement).first()
    
    def create_default_user_permissions(self, user_id: int) -> UserPermissions:
        """Create default permissions for a user"""
        default_role = self.get_default_role()
        
        user_perms = UserPermissions(
            user_id=user_id,
            role_id=default_role.id if default_role else None,
            created_at=datetime.utcnow()
        )
        
        self.session.add(user_perms)
        self.session.commit()
        return user_perms
    
    def has_permission(self, user_id: int, permission: str) -> bool:
        """Check if user has a specific permission"""
        # Check if user is legacy admin
        user_statement = select(User).where(User.id == user_id)
        user = self.session.exec(user_statement).first()
        if user and user.is_admin:
            return True  # Legacy admins have all permissions
        
        user_perms = self.get_user_permissions(user_id)
        if not user_perms:
            return False
        
        # Check dedicated user permission columns first (these override everything)
        if permission == PermissionFlags.REQUEST_MOVIES and user_perms.can_request_movies is not None:
            return user_perms.can_request_movies
        elif permission == PermissionFlags.REQUEST_TV and user_perms.can_request_tv is not None:
            return user_perms.can_request_tv
        elif permission == PermissionFlags.REQUEST_4K and user_perms.can_request_4k is not None:
            return user_perms.can_request_4k
        
        # Check custom permission override
        custom_perm = user_perms.has_custom_permission(permission)
        if custom_perm is not None:
            return custom_perm
        
        # Check role permissions
        role = self.get_user_role(user_id)
        if role:
            return role.has_permission(permission)
        
        return False
    
    def can_request_media_type(self, user_id: int, media_type: str) -> bool:
        """Check if user can request a specific media type"""
        permission_map = {
            'movie': PermissionFlags.REQUEST_MOVIES,
            'tv': PermissionFlags.REQUEST_TV
        }
        
        permission = permission_map.get(media_type.lower())
        if not permission:
            return False
        
        return self.has_permission(user_id, permission)
    
    def can_request_4k(self, user_id: int) -> bool:
        """Check if user can request 4K content"""
        return self.has_permission(user_id, PermissionFlags.REQUEST_4K)
    
    def should_auto_approve(self, user_id: int, media_type: str = None) -> bool:
        """Check if user's requests should be auto-approved"""
        if not media_type:
            # Check if user has any auto-approve permissions
            return (
                self.has_permission(user_id, PermissionFlags.REQUEST_AUTO_APPROVE_MOVIES) or
                self.has_permission(user_id, PermissionFlags.REQUEST_AUTO_APPROVE_TV) or
                self.has_permission(user_id, PermissionFlags.REQUEST_AUTO_APPROVE_4K)
            )
        
        # Check specific media type auto-approve permission
        permission_map = {
            'movie': PermissionFlags.REQUEST_AUTO_APPROVE_MOVIES,
            'tv': PermissionFlags.REQUEST_AUTO_APPROVE_TV,
        }
        
        permission = permission_map.get(media_type.lower())
        if permission:
            return self.has_permission(user_id, permission)
        
        return False
    
    def get_request_limit(self, user_id: int, global_default: int = 10) -> int:
        """Get user's request limit"""
        user_perms = self.get_user_permissions(user_id)
        if not user_perms:
            return global_default
        
        # Check for unlimited permission
        if self.has_permission(user_id, PermissionFlags.REQUEST_UNLIMITED):
            return 999999  # Effectively unlimited
        
        # Get role default
        role = self.get_user_role(user_id)
        role_default = global_default
        if role:
            role_perms = role.get_permissions()
            # Roles can define their own default limits
            role_default = role_perms.get('max_requests', global_default)
        
        return user_perms.get_effective_max_requests(role_default, global_default)
    
    def can_make_request(self, user_id: int, global_default: int = 10) -> tuple[bool, str]:
        """Check if user can make a new request. Returns (can_make, reason)"""
        user_perms = self.get_user_permissions(user_id)
        if not user_perms:
            return False, "User permissions not found"
        
        # Check if unlimited requests
        if self.has_permission(user_id, PermissionFlags.REQUEST_UNLIMITED):
            return True, ""
        
        # Check current request count
        max_requests = self.get_request_limit(user_id, global_default)
        if user_perms.current_request_count >= max_requests:
            return False, f"Request limit reached ({user_perms.current_request_count}/{max_requests})"
        
        return True, ""
    
    def increment_user_request_count(self, user_id: int) -> None:
        """Increment user's request count when a request is created"""
        user_perms = self.get_user_permissions(user_id)
        if user_perms:
            user_perms.increment_request_count()
            user_perms.updated_at = datetime.utcnow()
            self.session.add(user_perms)
            self.session.commit()
    
    def decrement_user_request_count(self, user_id: int) -> None:
        """Decrement user's request count when a request is approved/rejected"""
        user_perms = self.get_user_permissions(user_id)
        if user_perms:
            user_perms.decrement_request_count()
            user_perms.updated_at = datetime.utcnow()
            self.session.add(user_perms)
            self.session.commit()
    
    def sync_user_request_counts(self) -> None:
        """Sync all user request counts with actual database counts"""
        # Get all users with permissions
        statement = select(UserPermissions)
        all_user_perms = self.session.exec(statement).all()
        
        for user_perms in all_user_perms:
            # Count pending requests for this user
            request_statement = select(MediaRequest).where(
                MediaRequest.user_id == user_perms.user_id,
                MediaRequest.status == RequestStatus.PENDING
            )
            pending_count = len(self.session.exec(request_statement).all())
            
            # Update if different
            if user_perms.current_request_count != pending_count:
                user_perms.current_request_count = pending_count
                user_perms.updated_at = datetime.utcnow()
                self.session.add(user_perms)
        
        self.session.commit()
    
    def assign_role(self, user_id: int, role_id: int) -> bool:
        """Assign a role to a user"""
        try:
            user_perms = self.get_user_permissions(user_id)
            if user_perms:
                user_perms.role_id = role_id
                user_perms.updated_at = datetime.utcnow()
                self.session.add(user_perms)
                self.session.commit()
                return True
            return False
        except Exception:
            return False
    
    def set_user_permission(self, user_id: int, permission: str, enabled: bool) -> bool:
        """Set a specific permission for a user"""
        try:
            user_perms = self.get_user_permissions(user_id)
            if user_perms:
                user_perms.add_custom_permission(permission, enabled)
                user_perms.updated_at = datetime.utcnow()
                self.session.add(user_perms)
                self.session.commit()
                return True
            return False
        except Exception:
            return False
    
    def get_all_roles(self) -> List[Role]:
        """Get all available roles"""
        statement = select(Role).order_by(Role.name)
        return list(self.session.exec(statement).all())
    
    def get_user_effective_permissions(self, user_id: int) -> Dict[str, bool]:
        """Get all effective permissions for a user (role + custom overrides)"""
        # Start with role permissions
        role = self.get_user_role(user_id)
        permissions = role.get_permissions() if role else {}
        
        # Apply custom overrides
        user_perms = self.get_user_permissions(user_id)
        if user_perms:
            custom_perms = user_perms.get_custom_permissions()
            permissions.update(custom_perms)
        
        # Legacy admin override
        user_statement = select(User).where(User.id == user_id)
        user = self.session.exec(user_statement).first()
        if user and user.is_admin:
            # Give all admin permissions
            admin_perms = {perm: True for perm in PermissionFlags.get_admin_permissions()}
            permissions.update(admin_perms)
        
        return permissions