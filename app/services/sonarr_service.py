import httpx
from typing import Dict, List, Optional
from sqlmodel import Session

from ..services.settings_service import SettingsService


class SonarrService:
    def __init__(self, session: Session = None):
        if session is None:
            # Create a new session if none provided
            from ..core.database import engine
            self.session = Session(engine)
            self._owns_session = True
        else:
            self.session = session
            self._owns_session = False
        
        # Get configuration from ServiceInstance (new system) or fallback to legacy settings
        self.base_url = None
        self.api_key = None
        self.instance = None
        
        # Try new ServiceInstance system first
        from ..models.service_instance import ServiceInstance, ServiceType
        from sqlmodel import select
        
        statement = select(ServiceInstance).where(
            ServiceInstance.service_type == ServiceType.SONARR,
            ServiceInstance.is_enabled == True
        ).order_by(ServiceInstance.id)  # Use first enabled instance
        
        self.instance = self.session.exec(statement).first()
        
        if self.instance:
            # Use new ServiceInstance configuration
            raw_url = self.instance.url
            if raw_url and raw_url.strip():
                self.base_url = raw_url.strip().rstrip('/')
            else:
                self.base_url = None
            self.api_key = self.instance.api_key if self.instance.api_key else None
        else:
            # Fallback to legacy settings
            config = SettingsService.get_sonarr_config(self.session)
            raw_url = config.get('url', '')
            if raw_url and raw_url.strip():
                self.base_url = raw_url.strip().rstrip('/')
            else:
                self.base_url = None
            self.api_key = config.get('api_key', '') if config.get('api_key') else None
        
        self.headers = {
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        } if self.api_key else {}
    
    def __del__(self):
        if hasattr(self, '_owns_session') and self._owns_session and hasattr(self, 'session'):
            self.session.close()
    
    async def test_connection(self) -> bool:
        """Test connection to Sonarr"""
        if not self.base_url or not self.api_key:
            return False
            
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    f"{self.base_url}/api/v3/system/status",
                    headers=self.headers,
                    timeout=10
                )
                return response.status_code == 200
        except Exception as e:
            print(f"Sonarr connection test failed: {e}")
            return False
    
    async def get_root_folders(self) -> List[Dict]:
        """Get available root folders"""
        if not self.base_url or not self.api_key:
            return []
            
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    f"{self.base_url}/api/v3/rootfolder",
                    headers=self.headers,
                    timeout=10
                )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting Sonarr root folders: {e}")
            return []
    
    async def get_quality_profiles(self) -> List[Dict]:
        """Get available quality profiles"""
        if not self.base_url or not self.api_key:
            return []
            
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    f"{self.base_url}/api/v3/qualityprofile",
                    headers=self.headers,
                    timeout=10
                )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting Sonarr quality profiles: {e}")
            return []
    
    async def search_series(self, tmdb_id: int) -> Optional[Dict]:
        """Search for TV series by TMDB ID"""
        if not self.base_url:
            print("Sonarr error: No URL configured. Please set up Sonarr in the Services section.")
            return None
        if not self.api_key:
            print("Sonarr error: No API key configured. Please add an API key in the Services section.")
            return None
            
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    f"{self.base_url}/api/v3/series/lookup",
                    headers=self.headers,
                    params={'term': f'tmdb:{tmdb_id}'},
                    timeout=10
                )
                response.raise_for_status()
                results = response.json()
                return results[0] if results else None
        except Exception as e:
            print(f"Error searching series in Sonarr: {e}")
            return None
    
    async def add_series(self, tmdb_id: int, quality_profile_id: int = None, root_folder_path: str = None, monitor_type: str = 'all', user_id: int = None) -> Optional[Dict]:
        """Add TV series to Sonarr"""
        if not self.base_url:
            print("Sonarr error: No URL configured. Please set up Sonarr in the Services section.")
            return None
        if not self.api_key:
            print("Sonarr error: No API key configured. Please add an API key in the Services section.")
            return None
            
        try:
            # First search for the series
            series_data = await self.search_series(tmdb_id)
            if not series_data:
                print(f"❌ TV series not found in Sonarr search for TMDB ID: {tmdb_id}")
                return None
            
            print(f"🔍 Found TV series in Sonarr: {series_data.get('title', 'Unknown')} (TMDB: {tmdb_id})")
            
            # Check if series already exists in Sonarr
            existing_series = await self.get_series_by_tmdb_id(tmdb_id)
            if existing_series:
                print(f"⚠️ TV series already exists in Sonarr with ID: {existing_series.get('id')}")
                return existing_series  # Return existing series data instead of failing
            
            # Get default settings if not provided
            if not quality_profile_id:
                # First try user permissions
                if user_id:
                    from ..models.user_permissions import UserPermissions
                    from sqlmodel import select
                    user_perms_stmt = select(UserPermissions).where(UserPermissions.user_id == user_id)
                    user_perms = self.session.exec(user_perms_stmt).first()
                    if user_perms and user_perms.tv_quality_profile_id:
                        quality_profile_id = user_perms.tv_quality_profile_id
                
                # Then try service instance settings
                if not quality_profile_id and self.instance:
                    settings = self.instance.get_settings()
                    quality_profile_id = settings.get('quality_profile_id')
                
                # Finally fallback to first available
                if not quality_profile_id:
                    profiles = await self.get_quality_profiles()
                    if profiles:
                        quality_profile_id = profiles[0]['id']
                        print(f"🔍 Using default quality profile: {profiles[0].get('name', 'Unknown')} (ID: {quality_profile_id})")
                    else:
                        print("❌ No quality profiles available in Sonarr")
                        return None
            
            if not root_folder_path:
                # Try service instance settings first
                if self.instance:
                    settings = self.instance.get_settings()
                    root_folder_path = settings.get('root_folder_path')
                
                # Fallback to first available
                if not root_folder_path:
                    folders = await self.get_root_folders()
                    if folders:
                        root_folder_path = folders[0]['path']
                        print(f"🔍 Using default root folder: {root_folder_path}")
                    else:
                        print("❌ No root folders available in Sonarr")
                        return None
            
            # Get additional settings from service instance
            settings = self.instance.get_settings() if self.instance else {}
            monitored = settings.get('monitored', True)
            season_folder = settings.get('season_folder', True)
            search_for_missing = settings.get('search_for_missing_episodes', True)
            language_profile_id = settings.get('language_profile_id', 1)
            
            # Prepare series data for adding
            add_data = {
                'title': series_data['title'],
                'qualityProfileId': quality_profile_id,
                'rootFolderPath': root_folder_path,
                'tvdbId': series_data.get('tvdbId', 0),
                'monitored': monitored,
                'seasonFolder': season_folder,
                'languageProfileId': language_profile_id,
                'addOptions': {
                    'searchForMissingEpisodes': search_for_missing,
                    'searchForCutoffUnmetEpisodes': False
                }
            }
            
            # Add tags if configured
            tags = settings.get('tags', [])
            if tags:
                add_data['tags'] = tags
            
            # Set monitoring based on type
            if monitor_type == 'all':
                add_data['addOptions']['monitor'] = 'all'
            elif monitor_type == 'future':
                add_data['addOptions']['monitor'] = 'future'
            elif monitor_type == 'missing':
                add_data['addOptions']['monitor'] = 'missing'
            elif monitor_type == 'existing':
                add_data['addOptions']['monitor'] = 'existing'
            else:
                add_data['addOptions']['monitor'] = 'all'
            
            # Add any additional fields from the search result
            for field in ['year', 'images', 'overview', 'network', 'airTime', 'seriesType']:
                if field in series_data:
                    add_data[field] = series_data[field]
            
            print(f"🔍 Sonarr payload for '{series_data['title']}': {add_data}")
            
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.post(
                    f"{self.base_url}/api/v3/series",
                    headers=self.headers,
                    json=add_data,
                    timeout=15
                )
                
                if not response.is_success:
                    print(f"❌ Sonarr API error {response.status_code}: {response.text}")
                    print(f"🔍 Request URL: {response.url}")
                    print(f"🔍 Request headers: {self.headers}")
                
                response.raise_for_status()
                return response.json()
            
        except Exception as e:
            print(f"Error adding series to Sonarr: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"🔍 Response content: {e.response.text}")
            return None
    
    async def get_series_by_tmdb_id(self, tmdb_id: int) -> Optional[Dict]:
        """Check if series already exists in Sonarr"""
        if not self.base_url:
            print("Sonarr error: No URL configured. Please set up Sonarr in the Services section.")
            return None
        if not self.api_key:
            print("Sonarr error: No API key configured. Please add an API key in the Services section.")
            return None
            
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    f"{self.base_url}/api/v3/series",
                    headers=self.headers,
                    timeout=10
                )
                response.raise_for_status()
                series_list = response.json()
                
                # Sonarr doesn't always store TMDB ID, so we need to search by title as well
                search_result = await self.search_series(tmdb_id)
                if not search_result:
                    return None
                
                search_title = search_result.get('title', '').lower()
            
            for series in series_list:
                if (series.get('tmdbId') == tmdb_id or 
                    series.get('title', '').lower() == search_title):
                    return series
            return None
            
        except Exception as e:
            print(f"Error checking series in Sonarr: {e}")
            return None
    
    async def get_series_details(self, sonarr_id: int) -> Optional[Dict]:
        """Get detailed series information from Sonarr by internal ID"""
        if not self.base_url:
            print("Sonarr error: No URL configured. Please set up Sonarr in the Services section.")
            return None
        if not self.api_key:
            print("Sonarr error: No API key configured. Please add an API key in the Services section.")
            return None
            
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    f"{self.base_url}/api/v3/series/{sonarr_id}",
                    headers=self.headers,
                    timeout=10
                )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"Error getting series details from Sonarr: {e}")
            return None