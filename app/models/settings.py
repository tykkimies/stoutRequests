from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
import json


class Settings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Plex Configuration
    plex_url: Optional[str] = Field(default=None, max_length=500)
    plex_token: Optional[str] = Field(default=None, max_length=500)
    plex_client_id: str = Field(default="stout-requests", max_length=100)
    
    # TMDB Configuration
    tmdb_api_key: Optional[str] = Field(default=None, max_length=500)
    
    # Radarr Configuration  
    radarr_url: Optional[str] = Field(default=None, max_length=500)
    radarr_api_key: Optional[str] = Field(default=None, max_length=500)
    
    # Sonarr Configuration
    sonarr_url: Optional[str] = Field(default=None, max_length=500)
    sonarr_api_key: Optional[str] = Field(default=None, max_length=500)
    
    # Application Settings
    app_name: str = Field(default="Stout Requests", max_length=100)
    base_url: str = Field(default="", max_length=200)  # For reverse proxy support (e.g., "/stout")
    require_approval: bool = Field(default=True)
    auto_approve_admin: bool = Field(default=True)
    max_requests_per_user: int = Field(default=10)
    
    # Request Visibility Settings
    can_view_all_requests: bool = Field(default=False)  # Users can see all requests, not just their own
    can_view_request_user: bool = Field(default=False)  # Users can see who made each request
    
    # Library Sync Preferences (JSON field storing list of library names)
    sync_library_preferences: Optional[str] = Field(default=None, max_length=2000)
    
    # Background Job Settings (JSON field storing job configuration)
    background_job_settings: Optional[str] = Field(default=None, max_length=2000)
    
    # Theme Settings
    site_theme: str = Field(default="default", max_length=50)
    
    # Metadata
    is_configured: bool = Field(default=False)
    configured_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    def mask_sensitive_data(self) -> dict:
        """Return settings dict with masked sensitive data for display"""
        data = self.dict()
        
        # Mask sensitive fields
        sensitive_fields = ['plex_token', 'tmdb_api_key', 'radarr_api_key', 'sonarr_api_key']
        for field in sensitive_fields:
            if data.get(field):
                # Show first 8 characters then mask the rest
                value = data[field]
                data[field] = value[:8] + '•' * (len(value) - 8) if len(value) > 8 else '•' * len(value)
        
        return data
    
    def validate_urls(self) -> dict:
        """Validate URL formats"""
        errors = {}
        url_fields = ['plex_url', 'radarr_url', 'sonarr_url']
        
        for field in url_fields:
            url = getattr(self, field)
            if url:
                if not url.startswith(('http://', 'https://')):
                    errors[field] = "URL must start with http:// or https://"
                elif url.endswith('/'):
                    # Auto-fix trailing slashes
                    setattr(self, field, url.rstrip('/'))
        
        # Validate base URL
        if self.base_url:
            base_url = self.base_url.strip()
            # Must start with / if not empty
            if base_url and not base_url.startswith('/'):
                base_url = '/' + base_url
            # Remove trailing slash
            if base_url.endswith('/') and len(base_url) > 1:
                base_url = base_url.rstrip('/')
            # Auto-fix the base URL
            self.base_url = base_url
            
            # Additional validation
            if any(char in base_url for char in [' ', '?', '#', '&']):
                errors['base_url'] = "Base URL cannot contain spaces or query parameters"
        
        return errors
    
    def test_connections(self) -> dict:
        """Test connections to external services"""
        results = {
            'plex': {'status': 'not_configured', 'message': ''},
            'tmdb': {'status': 'not_configured', 'message': ''},
            'radarr': {'status': 'not_configured', 'message': ''},
            'sonarr': {'status': 'not_configured', 'message': ''}
        }
        
        # Test Plex connection
        if self.plex_url and self.plex_token:
            try:
                import requests
                response = requests.get(
                    f"{self.plex_url}/identity",
                    headers={'X-Plex-Token': self.plex_token},
                    timeout=10
                )
                if response.status_code == 200:
                    results['plex'] = {'status': 'connected', 'message': 'Connection successful'}
                else:
                    results['plex'] = {'status': 'error', 'message': f'HTTP {response.status_code}'}
            except Exception as e:
                results['plex'] = {'status': 'error', 'message': str(e)}
        
        # Test TMDB connection
        if self.tmdb_api_key:
            try:
                import requests
                response = requests.get(
                    "https://api.themoviedb.org/3/configuration",
                    params={'api_key': self.tmdb_api_key},
                    timeout=10
                )
                if response.status_code == 200:
                    results['tmdb'] = {'status': 'connected', 'message': 'Connection successful'}
                else:
                    results['tmdb'] = {'status': 'error', 'message': f'HTTP {response.status_code}'}
            except Exception as e:
                results['tmdb'] = {'status': 'error', 'message': str(e)}
        
        # Test Radarr connection
        if self.radarr_url and self.radarr_api_key:
            try:
                import requests
                response = requests.get(
                    f"{self.radarr_url}/api/v3/system/status",
                    headers={'X-Api-Key': self.radarr_api_key},
                    timeout=10
                )
                if response.status_code == 200:
                    results['radarr'] = {'status': 'connected', 'message': 'Connection successful'}
                else:
                    results['radarr'] = {'status': 'error', 'message': f'HTTP {response.status_code}'}
            except Exception as e:
                results['radarr'] = {'status': 'error', 'message': str(e)}
        
        # Test Sonarr connection
        if self.sonarr_url and self.sonarr_api_key:
            try:
                import requests
                response = requests.get(
                    f"{self.sonarr_url}/api/v3/system/status",
                    headers={'X-Api-Key': self.sonarr_api_key},
                    timeout=10
                )
                if response.status_code == 200:
                    results['sonarr'] = {'status': 'connected', 'message': 'Connection successful'}
                else:
                    results['sonarr'] = {'status': 'error', 'message': f'HTTP {response.status_code}'}
            except Exception as e:
                results['sonarr'] = {'status': 'error', 'message': str(e)}
        
        return results
    
    def get_sync_library_preferences(self) -> list:
        """Get list of library names to sync"""
        if not self.sync_library_preferences:
            return []
        try:
            return json.loads(self.sync_library_preferences)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_sync_library_preferences(self, library_names: list) -> None:
        """Set list of library names to sync"""
        self.sync_library_preferences = json.dumps(library_names) if library_names else None
    
    def should_sync_library(self, library_name: str) -> bool:
        """Check if a library should be synced based on preferences"""
        preferences = self.get_sync_library_preferences()
        # If no preferences are set, sync all libraries (default behavior)
        if not preferences:
            return True
        return library_name in preferences
    
    def get_background_job_settings(self) -> dict:
        """Get background job settings"""
        if not self.background_job_settings:
            return {}
        try:
            return json.loads(self.background_job_settings)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_background_job_settings(self, settings: dict) -> None:
        """Set background job settings"""
        self.background_job_settings = json.dumps(settings) if settings else None