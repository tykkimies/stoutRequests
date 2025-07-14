from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
import json


class Role(SQLModel, table=True):
    """User roles with configurable permissions"""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, max_length=50)  # "admin", "power_user", "basic_user", "limited"
    display_name: str = Field(max_length=100)  # "Administrator", "Power User", "Basic User", "Limited User"
    description: Optional[str] = Field(default=None, max_length=500)
    permissions: str = Field(default="{}")  # JSON field with permission flags
    is_default: bool = Field(default=False)  # Default role for new users
    is_system: bool = Field(default=False)  # System roles that cannot be deleted
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    def get_permissions(self) -> dict:
        """Get permissions as a dictionary"""
        try:
            return json.loads(self.permissions)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_permissions(self, permissions_dict: dict) -> None:
        """Set permissions from a dictionary"""
        self.permissions = json.dumps(permissions_dict) if permissions_dict else "{}"
    
    def has_permission(self, permission: str) -> bool:
        """Check if role has a specific permission"""
        perms = self.get_permissions()
        return perms.get(permission, False)
    
    def add_permission(self, permission: str) -> None:
        """Add a permission to this role"""
        perms = self.get_permissions()
        perms[permission] = True
        self.set_permissions(perms)
    
    def remove_permission(self, permission: str) -> None:
        """Remove a permission from this role"""
        perms = self.get_permissions()
        perms.pop(permission, None)
        self.set_permissions(perms)


class PermissionFlags:
    """Available permission flags for roles and users"""
    
    # Admin permissions
    ADMIN_FULL = "admin.full"
    ADMIN_MANAGE_USERS = "admin.manage_users"
    ADMIN_MANAGE_SETTINGS = "admin.manage_settings"
    ADMIN_MANAGE_ROLES = "admin.manage_roles"
    ADMIN_VIEW_ALL_REQUESTS = "admin.view_all_requests"
    ADMIN_APPROVE_REQUESTS = "admin.approve_requests"
    ADMIN_DELETE_REQUESTS = "admin.delete_requests"
    ADMIN_LIBRARY_SYNC = "admin.library_sync"
    ADMIN_OVERRIDE_USER_REQUESTS = "admin.override_user_requests"  # Request on behalf of others
    
    # Request permissions - Basic
    REQUEST_MOVIES = "request.movies"
    REQUEST_TV = "request.tv"
    REQUEST_4K = "request.4k"
    REQUEST_MUSIC = "request.music"  # Future: music requests
    
    # Request permissions - Advanced
    REQUEST_AUTO_APPROVE_MOVIES = "request.auto_approve.movies"
    REQUEST_AUTO_APPROVE_TV = "request.auto_approve.tv"
    REQUEST_AUTO_APPROVE_4K = "request.auto_approve.4k"
    REQUEST_AUTO_APPROVE_MUSIC = "request.auto_approve.music"
    REQUEST_UNLIMITED = "request.unlimited"  # Override request limits
    REQUEST_FOR_OTHERS = "request.for_others"  # Request content for other users
    
    # Request management
    REQUEST_MANAGE_OWN = "request.manage_own"  # Delete/edit own requests
    REQUEST_MANAGE_ALL = "request.manage_all"  # Delete/edit any requests
    REQUEST_VIEW_ALL = "request.view_all"  # View all users' requests
    REQUEST_VIEW_DETAILS = "request.view_details"  # View detailed request info
    REQUEST_VIEW_USERS = "request.view_users"  # See who made requests
    
    # Quality/Profile permissions
    QUALITY_MANAGE_PROFILES = "quality.manage_profiles"
    QUALITY_OVERRIDE_DEFAULTS = "quality.override_defaults"
    QUALITY_SET_CUSTOM_PATHS = "quality.set_custom_paths"  # Set custom download paths
    
    # Discovery permissions
    DISCOVER_BROWSE = "discover.browse"  # Browse discover sections
    DISCOVER_ADVANCED_FILTERS = "discover.advanced_filters"  # Use advanced filtering
    DISCOVER_WATCHLIST = "discover.watchlist"  # Manage personal watchlist
    
    # Notification permissions
    NOTIFICATIONS_RECEIVE = "notifications.receive"  # Receive notifications
    NOTIFICATIONS_MANAGE = "notifications.manage"  # Manage notification settings
    NOTIFICATIONS_WEBHOOK = "notifications.webhook"  # Manage webhook notifications
    
    # Integration permissions
    INTEGRATION_PLEX_SYNC = "integration.plex.sync"  # Sync with Plex library
    INTEGRATION_RADARR_MANAGE = "integration.radarr.manage"  # Manage Radarr integration
    INTEGRATION_SONARR_MANAGE = "integration.sonarr.manage"  # Manage Sonarr integration
    
    # User account permissions
    ACCOUNT_EDIT_PROFILE = "account.edit_profile"  # Edit own profile
    ACCOUNT_CHANGE_PASSWORD = "account.change_password"  # Change own password
    ACCOUNT_VIEW_ACTIVITY = "account.view_activity"  # View own activity log
    
    # System permissions
    SYSTEM_VIEW_LOGS = "system.view_logs"  # View system logs
    SYSTEM_MANAGE_BACKUPS = "system.manage_backups"  # Manage system backups
    SYSTEM_HEALTH_CHECK = "system.health_check"  # View system health
    
    # Content permissions
    CONTENT_VIEW_AVAILABLE = "content.view_available"  # See what's already in Plex
    CONTENT_VIEW_COLLECTION = "content.view_collection"  # Browse media collections
    CONTENT_RATE_REVIEW = "content.rate_review"  # Rate and review content
    
    @classmethod
    def get_all_permissions(cls) -> dict:
        """Get all available permissions with descriptions"""
        return {
            # Admin permissions
            cls.ADMIN_FULL: "Full administrative access",
            cls.ADMIN_MANAGE_USERS: "Manage user accounts and permissions",
            cls.ADMIN_MANAGE_SETTINGS: "Modify application settings",
            cls.ADMIN_MANAGE_ROLES: "Create and modify user roles",
            cls.ADMIN_VIEW_ALL_REQUESTS: "View all user requests",
            cls.ADMIN_APPROVE_REQUESTS: "Approve or reject media requests",
            cls.ADMIN_DELETE_REQUESTS: "Delete any media request",
            cls.ADMIN_LIBRARY_SYNC: "Manage Plex library synchronization",
            cls.ADMIN_OVERRIDE_USER_REQUESTS: "Make requests on behalf of other users",
            
            # Request permissions - Basic
            cls.REQUEST_MOVIES: "Request movies",
            cls.REQUEST_TV: "Request TV shows",
            cls.REQUEST_4K: "Request 4K quality content",
            cls.REQUEST_MUSIC: "Request music content",
            
            # Request permissions - Advanced
            cls.REQUEST_AUTO_APPROVE_MOVIES: "Auto-approve movie requests",
            cls.REQUEST_AUTO_APPROVE_TV: "Auto-approve TV show requests",
            cls.REQUEST_AUTO_APPROVE_4K: "Auto-approve 4K requests",
            cls.REQUEST_AUTO_APPROVE_MUSIC: "Auto-approve music requests",
            cls.REQUEST_UNLIMITED: "No request quantity limits",
            cls.REQUEST_FOR_OTHERS: "Request content for other users",
            
            # Request management
            cls.REQUEST_MANAGE_OWN: "Delete and edit own requests",
            cls.REQUEST_MANAGE_ALL: "Delete and edit any user's requests",
            cls.REQUEST_VIEW_ALL: "View all users' requests",
            cls.REQUEST_VIEW_DETAILS: "View detailed request information",
            cls.REQUEST_VIEW_USERS: "See who made each request",
            
            # Quality/Profile permissions
            cls.QUALITY_MANAGE_PROFILES: "Manage quality profiles",
            cls.QUALITY_OVERRIDE_DEFAULTS: "Override default quality settings",
            cls.QUALITY_SET_CUSTOM_PATHS: "Set custom download paths",
            
            # Discovery permissions
            cls.DISCOVER_BROWSE: "Browse discovery sections",
            cls.DISCOVER_ADVANCED_FILTERS: "Use advanced filtering options",
            cls.DISCOVER_WATCHLIST: "Manage personal watchlist",
            
            # Notification permissions
            cls.NOTIFICATIONS_RECEIVE: "Receive system notifications",
            cls.NOTIFICATIONS_MANAGE: "Manage notification preferences",
            cls.NOTIFICATIONS_WEBHOOK: "Configure webhook notifications",
            
            # Integration permissions
            cls.INTEGRATION_PLEX_SYNC: "Sync with Plex library",
            cls.INTEGRATION_RADARR_MANAGE: "Manage Radarr integration",
            cls.INTEGRATION_SONARR_MANAGE: "Manage Sonarr integration",
            
            # User account permissions
            cls.ACCOUNT_EDIT_PROFILE: "Edit own profile information",
            cls.ACCOUNT_CHANGE_PASSWORD: "Change own password",
            cls.ACCOUNT_VIEW_ACTIVITY: "View own activity history",
            
            # System permissions
            cls.SYSTEM_VIEW_LOGS: "View system logs",
            cls.SYSTEM_MANAGE_BACKUPS: "Manage system backups",
            cls.SYSTEM_HEALTH_CHECK: "View system health status",
            
            # Content permissions
            cls.CONTENT_VIEW_AVAILABLE: "View available content in Plex",
            cls.CONTENT_VIEW_COLLECTION: "Browse media collections",
            cls.CONTENT_RATE_REVIEW: "Rate and review content"
        }
    
    @classmethod
    def get_admin_permissions(cls) -> list:
        """Get list of admin-level permissions"""
        return [
            # All admin permissions
            cls.ADMIN_FULL,
            cls.ADMIN_MANAGE_USERS,
            cls.ADMIN_MANAGE_SETTINGS,
            cls.ADMIN_MANAGE_ROLES,
            cls.ADMIN_VIEW_ALL_REQUESTS,
            cls.ADMIN_APPROVE_REQUESTS,
            cls.ADMIN_DELETE_REQUESTS,
            cls.ADMIN_LIBRARY_SYNC,
            cls.ADMIN_OVERRIDE_USER_REQUESTS,
            
            # All request permissions
            cls.REQUEST_MOVIES,
            cls.REQUEST_TV,
            cls.REQUEST_4K,
            cls.REQUEST_MUSIC,
            cls.REQUEST_AUTO_APPROVE_MOVIES,
            cls.REQUEST_AUTO_APPROVE_TV,
            cls.REQUEST_AUTO_APPROVE_4K,
            cls.REQUEST_AUTO_APPROVE_MUSIC,
            cls.REQUEST_UNLIMITED,
            cls.REQUEST_FOR_OTHERS,
            cls.REQUEST_MANAGE_OWN,
            cls.REQUEST_MANAGE_ALL,
            cls.REQUEST_VIEW_ALL,
            cls.REQUEST_VIEW_DETAILS,
            cls.REQUEST_VIEW_USERS,
            
            # Quality permissions
            cls.QUALITY_MANAGE_PROFILES,
            cls.QUALITY_OVERRIDE_DEFAULTS,
            cls.QUALITY_SET_CUSTOM_PATHS,
            
            # Discovery permissions
            cls.DISCOVER_BROWSE,
            cls.DISCOVER_ADVANCED_FILTERS,
            cls.DISCOVER_WATCHLIST,
            
            # Notification permissions
            cls.NOTIFICATIONS_RECEIVE,
            cls.NOTIFICATIONS_MANAGE,
            cls.NOTIFICATIONS_WEBHOOK,
            
            # Integration permissions
            cls.INTEGRATION_PLEX_SYNC,
            cls.INTEGRATION_RADARR_MANAGE,
            cls.INTEGRATION_SONARR_MANAGE,
            
            # Account permissions
            cls.ACCOUNT_EDIT_PROFILE,
            cls.ACCOUNT_CHANGE_PASSWORD,
            cls.ACCOUNT_VIEW_ACTIVITY,
            
            # System permissions
            cls.SYSTEM_VIEW_LOGS,
            cls.SYSTEM_MANAGE_BACKUPS,
            cls.SYSTEM_HEALTH_CHECK,
            
            # Content permissions
            cls.CONTENT_VIEW_AVAILABLE,
            cls.CONTENT_VIEW_COLLECTION,
            cls.CONTENT_RATE_REVIEW
        ]
    
    @classmethod
    def get_basic_user_permissions(cls) -> list:
        """Get list of basic user permissions"""
        return [
            # Basic request permissions
            cls.REQUEST_MOVIES,
            cls.REQUEST_TV,
            cls.REQUEST_MANAGE_OWN,
            cls.REQUEST_VIEW_DETAILS,
            
            # Basic discovery
            cls.DISCOVER_BROWSE,
            cls.DISCOVER_WATCHLIST,
            
            # Basic account management
            cls.ACCOUNT_EDIT_PROFILE,
            cls.ACCOUNT_CHANGE_PASSWORD,
            cls.ACCOUNT_VIEW_ACTIVITY,
            
            # Basic notifications
            cls.NOTIFICATIONS_RECEIVE,
            cls.NOTIFICATIONS_MANAGE,
            
            # Basic content viewing
            cls.CONTENT_VIEW_AVAILABLE,
            cls.CONTENT_VIEW_COLLECTION,
            cls.CONTENT_RATE_REVIEW
        ]
    
    @classmethod
    def get_power_user_permissions(cls) -> list:
        """Get list of power user permissions"""
        return [
            # Enhanced request permissions
            cls.REQUEST_MOVIES,
            cls.REQUEST_TV,
            cls.REQUEST_4K,
            cls.REQUEST_AUTO_APPROVE_MOVIES,
            cls.REQUEST_AUTO_APPROVE_TV,
            cls.REQUEST_MANAGE_OWN,
            cls.REQUEST_VIEW_ALL,
            cls.REQUEST_VIEW_DETAILS,
            cls.REQUEST_VIEW_USERS,
            
            # Quality controls
            cls.QUALITY_OVERRIDE_DEFAULTS,
            cls.QUALITY_SET_CUSTOM_PATHS,
            
            # Advanced discovery
            cls.DISCOVER_BROWSE,
            cls.DISCOVER_ADVANCED_FILTERS,
            cls.DISCOVER_WATCHLIST,
            
            # Account management
            cls.ACCOUNT_EDIT_PROFILE,
            cls.ACCOUNT_CHANGE_PASSWORD,
            cls.ACCOUNT_VIEW_ACTIVITY,
            
            # Notifications
            cls.NOTIFICATIONS_RECEIVE,
            cls.NOTIFICATIONS_MANAGE,
            
            # Content viewing
            cls.CONTENT_VIEW_AVAILABLE,
            cls.CONTENT_VIEW_COLLECTION,
            cls.CONTENT_RATE_REVIEW
        ]
    
    @classmethod
    def get_moderator_permissions(cls) -> list:
        """Get list of moderator permissions"""
        return [
            # Request management
            cls.REQUEST_MOVIES,
            cls.REQUEST_TV,
            cls.REQUEST_4K,
            cls.REQUEST_AUTO_APPROVE_MOVIES,
            cls.REQUEST_AUTO_APPROVE_TV,
            cls.REQUEST_AUTO_APPROVE_4K,
            cls.REQUEST_MANAGE_OWN,
            cls.REQUEST_MANAGE_ALL,
            cls.REQUEST_VIEW_ALL,
            cls.REQUEST_VIEW_DETAILS,
            cls.REQUEST_VIEW_USERS,
            
            # Limited admin permissions
            cls.ADMIN_APPROVE_REQUESTS,
            cls.ADMIN_VIEW_ALL_REQUESTS,
            
            # Quality controls
            cls.QUALITY_OVERRIDE_DEFAULTS,
            cls.QUALITY_SET_CUSTOM_PATHS,
            
            # Discovery
            cls.DISCOVER_BROWSE,
            cls.DISCOVER_ADVANCED_FILTERS,
            cls.DISCOVER_WATCHLIST,
            
            # Account management
            cls.ACCOUNT_EDIT_PROFILE,
            cls.ACCOUNT_CHANGE_PASSWORD,
            cls.ACCOUNT_VIEW_ACTIVITY,
            
            # Notifications
            cls.NOTIFICATIONS_RECEIVE,
            cls.NOTIFICATIONS_MANAGE,
            
            # Content viewing
            cls.CONTENT_VIEW_AVAILABLE,
            cls.CONTENT_VIEW_COLLECTION,
            cls.CONTENT_RATE_REVIEW
        ]