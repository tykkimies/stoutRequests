from sqlmodel import Session, select
from typing import Optional
from datetime import datetime

from ..core.database import get_session
from ..models.settings import Settings


class SettingsService:
    """Service for managing application settings"""
    
    @staticmethod
    def get_settings(session: Session) -> Settings:
        """Get application settings (creates default if none exist)"""
        statement = select(Settings)
        settings = session.exec(statement).first()
        
        if not settings:
            # Create default settings
            settings = Settings()
            session.add(settings)
            session.commit()
            session.refresh(settings)
        
        return settings
    
    @staticmethod
    def update_settings(session: Session, settings_data: dict, user_id: Optional[int] = None) -> Settings:
        """Update application settings"""
        settings = SettingsService.get_settings(session)
        
        # Update fields
        for field, value in settings_data.items():
            if hasattr(settings, field):
                # Clean up URLs by removing trailing slashes
                if field.endswith('_url') and value:
                    value = value.rstrip('/')
                setattr(settings, field, value)
        
        # Update metadata
        settings.updated_at = datetime.utcnow()
        
        # Only set configured_by if a valid user_id is provided
        # During setup, there might not be any users yet
        if user_id is not None:
            # Check if user exists before setting foreign key
            from ..models.user import User
            from sqlmodel import select
            user_statement = select(User).where(User.id == user_id)
            user_exists = session.exec(user_statement).first()
            if user_exists:
                settings.configured_by = user_id
        
        settings.is_configured = True
        
        # Validate URLs
        errors = settings.validate_urls()
        if errors:
            raise ValueError(f"Validation errors: {errors}")
        
        session.add(settings)
        session.commit()
        session.refresh(settings)
        
        return settings
    
    @staticmethod
    def test_connections(session: Session) -> dict:
        """Test connections to all configured services"""
        settings = SettingsService.get_settings(session)
        return settings.test_connections()
    
    @staticmethod
    def is_configured(session: Session) -> bool:
        """Check if basic settings are configured"""
        settings = SettingsService.get_settings(session)
        
        # Check if minimum required settings are present (only Plex is required)
        required_fields = ['plex_url', 'plex_token']
        for field in required_fields:
            if not getattr(settings, field):
                return False
        
        return True
    
    @staticmethod
    def set_configured_by_first_user(session: Session) -> None:
        """Set the configured_by field to the first admin user (called after first login)"""
        settings = SettingsService.get_settings(session)
        
        if not settings.configured_by:
            from ..models.user import User
            from sqlmodel import select
            
            # Find the first admin user
            user_statement = select(User).where(User.is_admin == True).order_by(User.id)
            first_admin = session.exec(user_statement).first()
            
            if first_admin:
                settings.configured_by = first_admin.id
                settings.updated_at = datetime.utcnow()
                session.add(settings)
                session.commit()
    
    @staticmethod
    def get_plex_config(session: Session) -> dict:
        """Get Plex configuration"""
        settings = SettingsService.get_settings(session)
        return {
            'url': settings.plex_url,
            'token': settings.plex_token,
            'client_id': settings.plex_client_id
        }
    
    @staticmethod
    def get_tmdb_config(session: Session) -> dict:
        """Get TMDB configuration"""
        settings = SettingsService.get_settings(session)
        return {
            'api_key': settings.tmdb_api_key
        }
    
    @staticmethod
    def get_radarr_config(session: Session) -> dict:
        """Get Radarr configuration"""
        settings = SettingsService.get_settings(session)
        return {
            'url': settings.radarr_url,
            'api_key': settings.radarr_api_key
        }
    
    @staticmethod
    def get_sonarr_config(session: Session) -> dict:
        """Get Sonarr configuration"""
        settings = SettingsService.get_settings(session)
        return {
            'url': settings.sonarr_url,
            'api_key': settings.sonarr_api_key
        }
    
    @staticmethod
    def get_request_visibility_config(session: Session) -> dict:
        """Get request visibility configuration"""
        settings = SettingsService.get_settings(session)
        return {
            'can_view_all_requests': settings.can_view_all_requests,
            'can_view_request_user': settings.can_view_request_user
        }
    
    @staticmethod
    def get_base_url(session: Session) -> str:
        """Get the configured base URL for reverse proxy support"""
        settings = SettingsService.get_settings(session)
        return settings.base_url or ""
    
    @staticmethod
    def build_url(session: Session, path: str) -> str:
        """Build a URL with the configured base URL prefix"""
        base_url = SettingsService.get_base_url(session)
        
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
    
    @staticmethod
    def get_app_config(session: Session) -> dict:
        """Get general application configuration"""
        settings = SettingsService.get_settings(session)
        return {
            'app_name': settings.app_name,
            'base_url': settings.base_url,
            'site_theme': settings.site_theme,
            'require_approval': settings.require_approval,
            'auto_approve_admin': settings.auto_approve_admin,
            'max_requests_per_user': settings.max_requests_per_user
        }


# Global function to get settings from any context
def get_app_settings() -> Settings:
    """Get settings from database (for use in services)"""
    from ..core.database import engine
    
    with Session(engine) as session:
        return SettingsService.get_settings(session)


# Global function to build URLs with base URL (for use in API endpoints)
def build_app_url(path: str) -> str:
    """Build a URL with the configured base URL prefix (convenience function)"""
    from ..core.database import engine
    
    with Session(engine) as session:
        return SettingsService.build_url(session, path)