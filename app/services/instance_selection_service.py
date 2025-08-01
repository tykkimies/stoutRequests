"""
Instance Selection Service

Handles multi-instance support for media requests:
- Permission checking for instance access
- Smart instance selection based on user permissions and preferences
- 4K handling with dedicated vs profile-based instances
- Default instance fallback logic
"""

from typing import List, Optional, Dict, Any
from sqlmodel import Session, select
from app.models.service_instance import ServiceInstance, ServiceType
from app.models.user_permissions import UserPermissions
from app.models.media_request import MediaType
from app.models import User
from app.core.database import get_session

class InstanceSelectionService:
    """Service for managing multi-instance selection and permissions"""
    
    def __init__(self, session: Session):
        self.session = session
    
    async def get_available_instances(
        self, 
        user_id: int, 
        media_type: MediaType, 
        quality_tier: str = "standard"
    ) -> List[ServiceInstance]:
        """
        Get list of service instances available to a user for a specific media type and quality tier
        """
        # Get user and user permissions
        user = self.session.get(User, user_id)
        user_permissions = await self._get_user_permissions(user_id)
        
        print(f"🔍 Getting available instances for user {user.username if user else 'Unknown'} (ID: {user_id})")
        print(f"🔍 Media type: {media_type}, Quality tier: {quality_tier}")
        print(f"🔍 User is admin: {user.is_admin if user else False}")
        print(f"🔍 User is server owner: {user.is_server_owner if user else False}")
        
        # Determine required service type
        service_type = ServiceType.RADARR if media_type == MediaType.MOVIE else ServiceType.SONARR
        
        # Get all enabled instances for this service type
        statement = select(ServiceInstance).where(
            ServiceInstance.service_type == service_type,
            ServiceInstance.is_enabled == True
        ).order_by(
            ServiceInstance.is_default_movie.desc() if media_type == MediaType.MOVIE else ServiceInstance.is_default_tv.desc(),
            ServiceInstance.is_4k_default.desc() if quality_tier == "4k" else ServiceInstance.is_4k_default.asc(),
            ServiceInstance.name
        )
        
        instances = self.session.exec(statement).all()
        print(f"🔍 Found {len(instances)} total instances of type {service_type}")
        
        # Apply smart defaults and permissions
        available_instances = await self._apply_smart_defaults(user, user_permissions, instances, media_type, quality_tier)
        
        print(f"🔍 Final available instances: {[i.name for i in available_instances]}")
        return available_instances
    
    async def _apply_smart_defaults(
        self, 
        user: User, 
        user_permissions: Optional[UserPermissions], 
        instances: List[ServiceInstance],
        media_type: MediaType,
        quality_tier: str
    ) -> List[ServiceInstance]:
        """
        Apply smart default permissions based on user role and instance configuration
        """
        available_instances = []
        
        # Admin and server owner users get access to all instances
        if user and (user.is_admin or user.is_server_owner):
            print(f"🔓 Admin/Server Owner user gets access to all {len(instances)} instances")
            return instances
        
        # Check each instance for access
        for instance in instances:
            has_access = await self._user_has_instance_access(user_permissions, instance, quality_tier)
            if has_access:
                available_instances.append(instance)
        
        # If user has no explicit permissions but there are default instances, grant access
        if not available_instances and not user_permissions:
            print(f"🔍 No explicit permissions, checking for defaults")
            for instance in instances:
                # Grant access to default instances for basic users
                if ((media_type == MediaType.MOVIE and instance.is_default_movie) or 
                    (media_type == MediaType.TV and instance.is_default_tv)):
                    print(f"✅ Granting default access to {instance.name}")
                    available_instances.append(instance)
                # If only one instance exists, grant access
                elif len(instances) == 1:
                    print(f"✅ Only one instance exists, granting access to {instance.name}")
                    available_instances.append(instance)
        
        return available_instances
    
    async def setup_default_user_permissions(self, user_id: int) -> None:
        """
        Set up default instance permissions for a new user based on available instances
        """
        user = self.session.get(User, user_id)
        if not user:
            return
            
        # Don't set defaults for admin/server owner users - they get access to everything
        if user.is_admin or user.is_server_owner:
            return
            
        # Check if user already has permissions set up
        user_permissions = await self._get_user_permissions(user_id)
        if user_permissions and user_permissions.get_instance_permissions():
            return  # User already has instance permissions configured
        
        # Get all available instances
        all_instances = self.session.exec(
            select(ServiceInstance).where(ServiceInstance.is_enabled == True)
        ).all()
        
        if not all_instances:
            return  # No instances to configure
        
        # Create or update user permissions
        if not user_permissions:
            from ..models.user_permissions import UserPermissions
            user_permissions = UserPermissions(user_id=user_id)
            self.session.add(user_permissions)
        
        # Set up smart defaults
        default_permissions = {}
        
        # For basic users, give access to default instances
        radarr_instances = [i for i in all_instances if i.service_type == ServiceType.RADARR]
        sonarr_instances = [i for i in all_instances if i.service_type == ServiceType.SONARR]
        
        # Grant access to default movie instance
        for instance in radarr_instances:
            if instance.is_default_movie:
                default_permissions[f"instance_{instance.id}"] = True
                print(f"✅ Granted default movie instance access: {instance.name}")
                break
        else:
            # If no default, grant access to first radarr instance if only one exists
            if len(radarr_instances) == 1:
                default_permissions[f"instance_{radarr_instances[0].id}"] = True
                print(f"✅ Granted single movie instance access: {radarr_instances[0].name}")
        
        # Grant access to default TV instance
        for instance in sonarr_instances:
            if instance.is_default_tv:
                default_permissions[f"instance_{instance.id}"] = True
                print(f"✅ Granted default TV instance access: {instance.name}")
                break
        else:
            # If no default, grant access to first sonarr instance if only one exists
            if len(sonarr_instances) == 1:
                default_permissions[f"instance_{sonarr_instances[0].id}"] = True
                print(f"✅ Granted single TV instance access: {sonarr_instances[0].name}")
        
        # Save the default permissions
        if default_permissions:
            user_permissions.set_instance_permissions(default_permissions)
            from datetime import datetime
            user_permissions.updated_at = datetime.utcnow()
            self.session.commit()
            print(f"🔧 Set up default instance permissions for user {user.username}: {default_permissions}")
        
        return user_permissions
    
    async def select_best_instance(
        self, 
        user_id: int, 
        media_type: MediaType, 
        quality_tier: str = "standard",
        preferred_instance_id: Optional[int] = None
    ) -> Optional[ServiceInstance]:
        """
        Select the best instance for a request based on user preferences and permissions
        """
        available_instances = await self.get_available_instances(user_id, media_type, quality_tier)
        
        if not available_instances:
            return None
        
        # If user specified a preferred instance, use it if available
        if preferred_instance_id:
            for instance in available_instances:
                if instance.id == preferred_instance_id:
                    return instance
        
        # Selection priority:
        # 1. Default for media type + quality tier match
        # 2. Default for media type
        # 3. 4K default if requesting 4K
        # 4. First available instance
        
        # Look for media type default with matching quality tier
        for instance in available_instances:
            is_media_default = (
                (media_type == MediaType.MOVIE and instance.is_default_movie) or
                (media_type == MediaType.TV and instance.is_default_tv)
            )
            quality_match = (
                (quality_tier == "4k" and instance.is_4k_default) or
                (quality_tier != "4k" and not instance.is_4k_default) or
                instance.quality_tier == quality_tier
            )
            
            if is_media_default and quality_match:
                return instance
        
        # Look for media type default (any quality)
        for instance in available_instances:
            if (media_type == MediaType.MOVIE and instance.is_default_movie) or \
               (media_type == MediaType.TV and instance.is_default_tv):
                return instance
        
        # Look for 4K default if requesting 4K
        if quality_tier == "4k":
            for instance in available_instances:
                if instance.is_4k_default:
                    return instance
        
        # Return first available instance
        return available_instances[0]
    
    async def get_user_instance_permissions(self, user_id: int) -> Dict[str, Any]:
        """
        Get comprehensive instance permissions for a user
        """
        user_permissions = await self._get_user_permissions(user_id)
        
        if not user_permissions:
            return {
                "has_instance_permissions": False,
                "can_request_4k": False,
                "allowed_instances": [],
                "allowed_categories": []
            }
        
        instance_perms = user_permissions.get_instance_permissions()
        
        # Extract allowed instances and categories
        allowed_instances = []
        allowed_categories = []
        
        for key, value in instance_perms.items():
            if value:  # Only include if permission is True
                if key.startswith("instance_"):
                    allowed_instances.append(int(key.replace("instance_", "")))
                elif key.startswith("category_"):
                    allowed_categories.append(key.replace("category_", ""))
        
        return {
            "has_instance_permissions": bool(instance_perms),
            "can_request_4k": user_permissions.has_category_access("4k"),
            "allowed_instances": allowed_instances,
            "allowed_categories": allowed_categories,
            "legacy_4k_permission": user_permissions.can_request_4k
        }
    
    async def validate_instance_access(
        self, 
        user_id: int, 
        instance_id: int, 
        media_type: MediaType,
        quality_tier: str = "standard"
    ) -> bool:
        """
        Validate that a user has access to a specific instance for a request
        """
        # Get the instance
        instance = self.session.get(ServiceInstance, instance_id)
        if not instance or not instance.is_enabled:
            return False
        
        # Check media type compatibility
        if not instance.supports_media_type(media_type.value):
            return False
        
        # Get user permissions
        user_permissions = await self._get_user_permissions(user_id)
        
        return await self._user_has_instance_access(user_permissions, instance, quality_tier)
    
    async def get_instance_categories(self) -> List[str]:
        """
        Get list of all instance categories in use
        """
        statement = select(ServiceInstance.instance_category).where(
            ServiceInstance.instance_category.isnot(None),
            ServiceInstance.is_enabled == True
        ).distinct()
        
        categories = self.session.exec(statement).all()
        return [cat for cat in categories if cat]
    
    async def get_default_instances(self) -> Dict[str, ServiceInstance]:
        """
        Get current default instances for each media type and quality tier
        """
        defaults = {}
        
        # Get movie defaults
        movie_default = self.session.exec(
            select(ServiceInstance).where(
                ServiceInstance.service_type == ServiceType.RADARR,
                ServiceInstance.is_default_movie == True,
                ServiceInstance.is_enabled == True
            )
        ).first()
        
        if movie_default:
            defaults["movie"] = movie_default
        
        # Get TV defaults
        tv_default = self.session.exec(
            select(ServiceInstance).where(
                ServiceInstance.service_type == ServiceType.SONARR,
                ServiceInstance.is_default_tv == True,
                ServiceInstance.is_enabled == True
            )
        ).first()
        
        if tv_default:
            defaults["tv"] = tv_default
        
        # Get 4K defaults
        fourk_movie_default = self.session.exec(
            select(ServiceInstance).where(
                ServiceInstance.service_type == ServiceType.RADARR,
                ServiceInstance.is_4k_default == True,
                ServiceInstance.is_enabled == True
            )
        ).first()
        
        if fourk_movie_default:
            defaults["4k_movie"] = fourk_movie_default
        
        fourk_tv_default = self.session.exec(
            select(ServiceInstance).where(
                ServiceInstance.service_type == ServiceType.SONARR,
                ServiceInstance.is_4k_default == True,
                ServiceInstance.is_enabled == True
            )
        ).first()
        
        if fourk_tv_default:
            defaults["4k_tv"] = fourk_tv_default
        
        return defaults
    
    # Private helper methods
    
    async def _get_user_permissions(self, user_id: int) -> Optional[UserPermissions]:
        """Get user permissions object"""
        return self.session.get(UserPermissions, user_id)
    
    async def _user_has_instance_access(
        self, 
        user_permissions: Optional[UserPermissions], 
        instance: ServiceInstance,
        quality_tier: str = "standard"
    ) -> bool:
        """
        Check if user has access to a specific instance
        """
        # Get user to check if they're admin
        user = self.session.get(User, user_permissions.user_id if user_permissions else None)
        
        # Admins and server owners have access to all instances
        if user and (user.is_admin or user.is_server_owner):
            print(f"🔓 Admin/Server Owner user {user.username} granted access to instance {instance.name}")
            return True
        
        if not user_permissions:
            # For users without permissions record, give access to default instances
            print(f"🔍 No permissions record for user, checking defaults for instance {instance.name}")
            if instance.is_default_movie or instance.is_default_tv:
                print(f"✅ Granting access to default instance {instance.name}")
                return True
            # If only one instance of this type exists, grant access
            from ..models.service_instance import ServiceType
            same_type_count = len(self.session.exec(
                select(ServiceInstance).where(
                    ServiceInstance.service_type == instance.service_type,
                    ServiceInstance.is_enabled == True
                )
            ).all())
            if same_type_count == 1:
                print(f"✅ Only one {instance.service_type} instance, granting access to {instance.name}")
                return True
            return False
        
        # Check specific instance permission first
        if user_permissions.has_instance_access(instance.id):
            print(f"✅ User has direct instance access to {instance.name}")
            return True
        
        # Check category permission
        instance_category = instance.get_effective_category()
        if user_permissions.has_category_access(instance_category):
            print(f"✅ User has category access ({instance_category}) to {instance.name}")
            return True
        
        # Legacy 4K permissions have been removed - all access is now instance/category based
        
        # No access - user has permissions record but no specific access to this instance
        
        print(f"❌ User denied access to {instance.name}")
        return False


# Service factory function
async def get_instance_selection_service() -> InstanceSelectionService:
    """Get instance selection service with database session"""
    session = next(get_session())
    return InstanceSelectionService(session)

# Convenience functions for common operations
async def get_user_available_instances(
    user_id: int, 
    media_type: MediaType, 
    quality_tier: str = "standard"
) -> List[ServiceInstance]:
    """Get available instances for a user - convenience function"""
    service = await get_instance_selection_service()
    return await service.get_available_instances(user_id, media_type, quality_tier)

async def select_instance_for_request(
    user_id: int, 
    media_type: MediaType, 
    quality_tier: str = "standard",
    preferred_instance_id: Optional[int] = None
) -> Optional[ServiceInstance]:
    """Select best instance for a request - convenience function"""
    service = await get_instance_selection_service()
    return await service.select_best_instance(user_id, media_type, quality_tier, preferred_instance_id)