from sqlmodel import SQLModel, Field, Relationship
from typing import Optional
from datetime import datetime
import json


class UserPermissions(SQLModel, table=True):
    """User-specific permission overrides and settings"""
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    role_id: Optional[int] = Field(default=None, foreign_key="role.id")
    
    # Custom permission overrides (JSON field)
    custom_permissions: Optional[str] = Field(default=None, max_length=2000)
    
    # Request limits and controls
    max_requests: Optional[int] = Field(default=None)  # Override global limit, None = use role default
    auto_approve_enabled: bool = Field(default=False)
    
    # Media type permissions
    can_request_movies: Optional[bool] = Field(default=None)  # None = use role default
    can_request_tv: Optional[bool] = Field(default=None)
    can_request_4k: Optional[bool] = Field(default=None)  # DEPRECATED: Use instance-based permissions instead
    
    # Instance-based permissions (JSON field)
    instance_permissions: Optional[str] = Field(default=None, max_length=2000)  # JSON field for granular instance access
    
    # Quality profile overrides (for Radarr/Sonarr integration)
    movie_quality_profile_id: Optional[int] = Field(default=None)
    tv_quality_profile_id: Optional[int] = Field(default=None)
    
    # Request quotas and tracking
    current_request_count: int = Field(default=0)  # Track current pending requests
    total_requests_made: int = Field(default=0)  # Historical count
    
    # Advanced settings
    request_retention_days: Optional[int] = Field(default=None)  # How long to keep request history
    notification_enabled: bool = Field(default=True)  # Future: email/push notifications
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    def get_custom_permissions(self) -> dict:
        """Get custom permissions as a dictionary"""
        if not self.custom_permissions:
            return {}
        try:
            return json.loads(self.custom_permissions)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_custom_permissions(self, permissions_dict: dict) -> None:
        """Set custom permissions from a dictionary"""
        self.custom_permissions = json.dumps(permissions_dict) if permissions_dict else None
    
    def has_custom_permission(self, permission: str) -> Optional[bool]:
        """Check if user has a custom permission override. Returns None if not set."""
        perms = self.get_custom_permissions()
        return perms.get(permission)
    
    def add_custom_permission(self, permission: str, enabled: bool = True) -> None:
        """Add or update a custom permission"""
        perms = self.get_custom_permissions()
        perms[permission] = enabled
        self.set_custom_permissions(perms)
    
    def remove_custom_permission(self, permission: str) -> None:
        """Remove a custom permission override"""
        perms = self.get_custom_permissions()
        perms.pop(permission, None)
        self.set_custom_permissions(perms)
    
    def get_effective_max_requests(self, role_default: int = 10, global_default: int = 10) -> int:
        """Get effective request limit considering role and user overrides"""
        if self.max_requests is not None:
            return self.max_requests
        return role_default if role_default is not None else global_default
    
    def can_make_request(self, role_default: int = 10, global_default: int = 10) -> bool:
        """Check if user can make a new request based on current count and limits"""
        max_requests = self.get_effective_max_requests(role_default, global_default)
        return self.current_request_count < max_requests
    
    def increment_request_count(self) -> None:
        """Increment current request count (call when request is created)"""
        self.current_request_count += 1
        self.total_requests_made += 1
    
    def decrement_request_count(self) -> None:
        """Decrement current request count (call when request is approved/rejected)"""
        if self.current_request_count > 0:
            self.current_request_count -= 1
    
    def reset_request_count(self) -> None:
        """Reset current request count to 0"""
        self.current_request_count = 0
    
    def get_instance_permissions(self) -> dict:
        """Get instance permissions as a dictionary"""
        if not self.instance_permissions:
            return {}
        try:
            return json.loads(self.instance_permissions)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_instance_permissions(self, permissions_dict: dict) -> None:
        """Set instance permissions from a dictionary"""
        self.instance_permissions = json.dumps(permissions_dict) if permissions_dict else None
    
    def has_instance_access(self, instance_id: int) -> bool:
        """Check if user has access to specific instance"""
        perms = self.get_instance_permissions()
        # Check specific instance access
        instance_access = perms.get(f"instance_{instance_id}")
        if instance_access is not None:
            return instance_access
        
        # If no specific permission set, deny access by default
        # Users must be explicitly granted instance permissions
        return False
    
    def has_category_access(self, category: str) -> bool:
        """Check if user has access to instances in a specific category"""
        perms = self.get_instance_permissions()
        category_access = perms.get(f"category_{category}")
        if category_access is not None:
            return category_access
        
        return False  # Default to denying access - users must be explicitly granted category permissions
    
    def add_instance_permission(self, instance_id: int, enabled: bool = True) -> None:
        """Add or update permission for a specific instance"""
        perms = self.get_instance_permissions()
        perms[f"instance_{instance_id}"] = enabled
        self.set_instance_permissions(perms)
    
    def add_category_permission(self, category: str, enabled: bool = True) -> None:
        """Add or update permission for a category of instances"""
        perms = self.get_instance_permissions()
        perms[f"category_{category}"] = enabled
        self.set_instance_permissions(perms)
    
    def remove_instance_permission(self, instance_id: int) -> None:
        """Remove permission override for a specific instance"""
        perms = self.get_instance_permissions()
        perms.pop(f"instance_{instance_id}", None)
        self.set_instance_permissions(perms)
    
    def remove_category_permission(self, category: str) -> None:
        """Remove permission override for a category"""
        perms = self.get_instance_permissions()
        perms.pop(f"category_{category}", None)
        self.set_instance_permissions(perms)
    
    def get_effective_media_permissions(self, role_permissions: dict = None) -> dict:
        """Get effective media type permissions considering role defaults and user overrides"""
        if role_permissions is None:
            role_permissions = {}
        
        return {
            'can_request_movies': (
                self.can_request_movies if self.can_request_movies is not None 
                else role_permissions.get('request.movies', True)
            ),
            'can_request_tv': (
                self.can_request_tv if self.can_request_tv is not None 
                else role_permissions.get('request.tv', True)
            ),
        }