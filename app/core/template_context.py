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


def get_global_template_context() -> dict:
    """Get global template context that should be available to all templates"""
    try:
        session = SQLSession(engine)
        settings = SettingsService.get_settings(session)
        
        # Create a URL helper function that uses the base URL from settings
        def url_for_with_base(path: str) -> str:
            return url_for(path, settings.base_url)
        
        # Ensure base_url doesn't create double slashes when empty
        base_url = settings.base_url.rstrip('/') if settings.base_url else ''
        
        result = {
            "site_theme": settings.site_theme,
            "app_name": settings.app_name,
            "base_url": base_url,
            "url_for": url_for_with_base
        }
        session.close()
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
            "url_for": fallback_url_for
        }