from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum
import json


class ServiceType(str, Enum):
    RADARR = "radarr"
    SONARR = "sonarr"
    LIDARR = "lidarr"  # Future support
    READARR = "readarr"  # Future support


class ServiceInstance(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Basic configuration
    name: str = Field(max_length=100)  # User-defined name (e.g., "Radarr 4K", "Sonarr Anime")
    service_type: ServiceType
    url: str = Field(max_length=500)
    api_key: str = Field(max_length=500)
    
    # Service settings
    is_enabled: bool = Field(default=True)
    
    # Multi-instance configuration
    is_default_movie: bool = Field(default=False)  # Default instance for movie requests
    is_default_tv: bool = Field(default=False)  # Default instance for TV requests
    is_4k_default: bool = Field(default=False)  # Default instance for 4K requests
    instance_category: Optional[str] = Field(default=None, max_length=50)  # e.g., "4k", "anime", "foreign"
    quality_tier: Optional[str] = Field(default="standard", max_length=20)  # "standard", "4k", "hdr"
    
    # Radarr/Sonarr specific settings (stored as JSON for flexibility)
    settings: Optional[str] = Field(default=None, max_length=2000)  # JSON field
    
    # Connection status
    last_test_result: Optional[str] = Field(default=None, max_length=1000)  # JSON result
    last_tested_at: Optional[datetime] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    
    def get_settings(self) -> dict:
        """Get service-specific settings from JSON"""
        if not self.settings:
            return {}
        try:
            return json.loads(self.settings)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_settings(self, settings_dict: dict) -> None:
        """Set service-specific settings as JSON"""
        self.settings = json.dumps(settings_dict) if settings_dict else None
    
    def get_test_result(self) -> dict:
        """Get last connection test result"""
        if not self.last_test_result:
            return {"status": "not_tested", "message": "Not tested yet"}
        try:
            return json.loads(self.last_test_result)
        except (json.JSONDecodeError, TypeError):
            return {"status": "error", "message": "Invalid test result data"}
    
    def set_test_result(self, result: dict) -> None:
        """Set connection test result"""
        self.last_test_result = json.dumps(result)
        self.last_tested_at = datetime.utcnow()
    
    def get_effective_category(self) -> str:
        """Get effective category for this instance"""
        if self.instance_category:
            return self.instance_category
        if self.is_4k_default:
            return "4k"
        return "standard"
    
    def supports_media_type(self, media_type: str) -> bool:
        """Check if this instance supports the given media type"""
        if media_type.lower() == "movie":
            return self.service_type == ServiceType.RADARR
        elif media_type.lower() == "tv":
            return self.service_type == ServiceType.SONARR
        return False
    
    def is_default_for_media_type(self, media_type: str) -> bool:
        """Check if this is the default instance for the given media type"""
        if media_type.lower() == "movie":
            return self.is_default_movie
        elif media_type.lower() == "tv":
            return self.is_default_tv
        return False
    
    def get_quality_tier_priority(self) -> int:
        """Get priority order for quality tiers (higher = better quality)"""
        tier_priorities = {
            "standard": 1,
            "4k": 2,
            "hdr": 3
        }
        return tier_priorities.get(self.quality_tier or "standard", 1)
    
    def mask_sensitive_data(self) -> dict:
        """Return instance dict with masked API key"""
        data = self.dict()
        if data.get('api_key'):
            # Show first 8 characters then mask the rest
            value = data['api_key']
            data['api_key'] = value[:8] + '•' * (len(value) - 8) if len(value) > 8 else '•' * len(value)
        return data
    
    async def test_connection(self) -> dict:
        """Test connection to the service"""
        try:
            import httpx
            
            # Get connection settings
            settings = self.get_settings()
            
            # Build URL from components if hostname/port are configured
            hostname = settings.get('hostname')
            port = settings.get('port')
            use_ssl = settings.get('use_ssl', False)
            url_base = settings.get('base_url', '').strip('/')
            
            if hostname and port:
                # Build URL from components (Ombi-style)
                protocol = 'https' if use_ssl else 'http'
                base_url = f"{protocol}://{hostname}:{port}"
                if url_base:
                    base_url = f"{base_url}/{url_base}"
            else:
                # Use legacy URL field (fallback)
                base_url = self.url.rstrip('/')
                if url_base:
                    base_url = f"{base_url}/{url_base}"
            
            # Determine API endpoint based on service type
            if self.service_type in [ServiceType.RADARR, ServiceType.SONARR]:
                endpoint = f"{base_url}/api/v3/system/status"
            else:
                # Future service types
                endpoint = f"{base_url}/api/system/status"
            
            async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:  # Allow self-signed certificates and follow redirects
                response = await client.get(
                    endpoint,
                    headers={'X-Api-Key': self.api_key},
                    timeout=10
                )
            
            if response.status_code == 200:
                data = response.json()
                result = {
                    "status": "connected",
                    "message": "Connection successful",
                    "version": data.get("version", "Unknown"),
                    "instance_name": data.get("instanceName", self.name)
                }
            elif response.status_code == 401:
                result = {
                    "status": "error",
                    "message": "Authentication failed - check your API key"
                }
            elif response.status_code == 404:
                result = {
                    "status": "error", 
                    "message": "API endpoint not found - check your URL and base URL configuration"
                }
            else:
                result = {
                    "status": "error",
                    "message": f"HTTP {response.status_code}: {response.text[:200]}"
                }
                
        except httpx.ConnectError as e:
            result = {
                "status": "error",
                "message": f"Connection failed: Cannot reach {base_url}"
            }
        except httpx.TimeoutException as e:
            result = {
                "status": "error",
                "message": "Connection timeout - service may be slow or unreachable"
            }
        except Exception as e:
            result = {
                "status": "error",
                "message": f"Connection failed: {str(e)}"
            }
        
        # Store the test result
        self.set_test_result(result)
        return result
    
    async def get_quality_profiles(self) -> list:
        """Get available quality profiles from the service"""
        try:
            import httpx
            
            endpoint = f"{self.url}/api/v3/qualityprofile"
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    endpoint,
                    headers={'X-Api-Key': self.api_key},
                    timeout=10
                )
            
            if response.status_code == 200:
                return response.json()
            else:
                return []
                
        except Exception as e:
            print(f"Error fetching quality profiles from {self.name}: {e}")
            return []
    
    async def get_root_folders(self) -> list:
        """Get available root folders from the service"""
        try:
            import httpx
            
            endpoint = f"{self.url}/api/v3/rootfolder"
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    endpoint,
                    headers={'X-Api-Key': self.api_key},
                    timeout=10
                )
            
            if response.status_code == 200:
                return response.json()
            else:
                return []
                
        except Exception as e:
            print(f"Error fetching root folders from {self.name}: {e}")
            return []
    
    async def get_tags(self) -> list:
        """Get available tags from the service"""
        try:
            import httpx
            
            endpoint = f"{self.url}/api/v3/tag"
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    endpoint,
                    headers={'X-Api-Key': self.api_key},
                    timeout=10
                )
            
            if response.status_code == 200:
                return response.json()
            else:
                return []
                
        except Exception as e:
            print(f"Error fetching tags from {self.name}: {e}")
            return []


# Default settings schemas for different service types
RADARR_DEFAULT_SETTINGS = {
    # Service Connection
    "hostname": None,  # Separate hostname/IP
    "port": 7878,  # Default Radarr port
    "use_ssl": False,  # HTTP vs HTTPS
    "base_url": None,  # For reverse proxy setups like /radarr
    
    # Content Settings
    "quality_profile_id": None,
    "root_folder_path": None,
    "minimum_availability": "inCinemas",  # announced, inCinemas, released, preDB
    "tags": [],
    
    # Automation Settings
    "monitored": True,
    "search_for_movie": True,  # Enable Automatic Search
    "enable_scan": True,  # Enable Scan - refreshes metadata and checks for files
    "enable_automatic_search": True,  # Enable Automatic Search for new releases
    "enable_integration": True  # Enable automatic integration when requests are approved
}

SONARR_DEFAULT_SETTINGS = {
    # Service Connection
    "hostname": None,  # Separate hostname/IP
    "port": 8989,  # Default Sonarr port
    "use_ssl": False,  # HTTP vs HTTPS
    "base_url": None,  # For reverse proxy setups like /sonarr
    
    # Content Settings
    "quality_profile_id": None,
    "root_folder_path": None,
    "language_profile_id": 1,  # Usually English
    "minimum_availability": "inCinemas",  # Same options as Radarr for consistency
    "tags": [],
    
    # Automation Settings  
    "monitored": True,
    "season_folder": True,
    "enable_scan": True,  # Enable Scan - refreshes metadata and checks for files
    "enable_automatic_search": True,  # Enable Automatic Search for new releases
    "enable_integration": True  # Enable automatic integration when requests are approved
}