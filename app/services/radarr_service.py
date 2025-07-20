import httpx
from typing import Dict, List, Optional
from sqlmodel import Session

from ..services.settings_service import SettingsService


class RadarrService:
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
            ServiceInstance.service_type == ServiceType.RADARR,
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
            config = SettingsService.get_radarr_config(self.session)
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
        """Test connection to Radarr"""
        if not self.base_url or not self.api_key:
            return False
            
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    f"{self.base_url}/api/v3/system/status",
                    headers=self.headers,
                    timeout=10
                )
                return response.is_success
        except Exception as e:
            print(f"Radarr connection test failed: {e}")
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
            print(f"Error getting Radarr root folders: {e}")
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
            print(f"Error getting Radarr quality profiles: {e}")
            return []
    
    async def search_movie(self, tmdb_id: int) -> Optional[Dict]:
        """Search for movie by TMDB ID"""
        if not self.base_url:
            print("Radarr error: No URL configured. Please set up Radarr in the Services section.")
            return None
        if not self.api_key:
            print("Radarr error: No API key configured. Please add an API key in the Services section.")
            return None
            
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    f"{self.base_url}/api/v3/movie/lookup",
                    headers=self.headers,
                    params={'term': f'tmdb:{tmdb_id}'},
                    timeout=10
                )
                response.raise_for_status()
                results = response.json()
                return results[0] if results else None
        except Exception as e:
            print(f"Error searching movie in Radarr: {e}")
            return None
    
    async def add_movie(self, tmdb_id: int, quality_profile_id: int = None, root_folder_path: str = None, user_id: int = None) -> Optional[Dict]:
        """Add movie to Radarr"""
        if not self.base_url:
            print("Radarr error: No URL configured. Please set up Radarr in the Services section.")
            return None
        if not self.api_key:
            print("Radarr error: No API key configured. Please add an API key in the Services section.")
            return None
            
        try:
            # First search for the movie
            movie_data = await self.search_movie(tmdb_id)
            if not movie_data:
                print(f"❌ Movie not found in Radarr search for TMDB ID: {tmdb_id}")
                return None
            
            print(f"🔍 Found movie in Radarr: {movie_data.get('title', 'Unknown')} (TMDB: {tmdb_id})")
            
            # Check if movie already exists in Radarr
            existing_movie = await self.get_movie_by_tmdb_id(tmdb_id)
            if existing_movie:
                print(f"⚠️ Movie already exists in Radarr with ID: {existing_movie.get('id')}")
                return existing_movie  # Return existing movie data instead of failing
            
            # Get default settings if not provided
            if not quality_profile_id:
                # First try user permissions
                if user_id:
                    from ..models.user_permissions import UserPermissions
                    from sqlmodel import select
                    user_perms_stmt = select(UserPermissions).where(UserPermissions.user_id == user_id)
                    user_perms = self.session.exec(user_perms_stmt).first()
                    if user_perms and user_perms.movie_quality_profile_id:
                        quality_profile_id = user_perms.movie_quality_profile_id
                
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
                        print("❌ No quality profiles available in Radarr")
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
                        print("❌ No root folders available in Radarr")
                        return None
            
            # Get additional settings from service instance
            settings = self.instance.get_settings() if self.instance else {}
            minimum_availability = settings.get('minimum_availability', 'released')
            monitored = settings.get('monitored', True)
            search_for_movie = settings.get('search_for_movie', True)
            
            # Prepare movie data for adding - ensure required fields are present
            add_data = {
                'title': movie_data.get('title', 'Unknown Title'),
                'qualityProfileId': quality_profile_id,
                'rootFolderPath': root_folder_path,
                'tmdbId': tmdb_id,
                'monitored': monitored,
                'minimumAvailability': minimum_availability,
                'addOptions': {
                    'searchForMovie': search_for_movie
                }
            }
            
            # Add required fields from movie lookup
            if 'year' in movie_data:
                add_data['year'] = movie_data['year']
            if 'titleSlug' in movie_data:
                add_data['titleSlug'] = movie_data['titleSlug']
            
            # Add optional fields if present
            optional_fields = ['images', 'runtime', 'overview', 'studio', 'genres', 'ratings']
            for field in optional_fields:
                if field in movie_data and movie_data[field] is not None:
                    add_data[field] = movie_data[field]
            
            # Add tags if configured
            tags = settings.get('tags', [])
            if tags:
                add_data['tags'] = tags
            
            print(f"🔍 Radarr payload for '{movie_data['title']}': {add_data}")
            
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.post(
                    f"{self.base_url}/api/v3/movie",
                    headers=self.headers,
                    json=add_data,
                    timeout=15
                )
                
                if not response.is_success:
                    print(f"❌ Radarr API error {response.status_code}: {response.text}")
                    print(f"🔍 Request URL: {response.url}")
                    print(f"🔍 Request headers: {self.headers}")
                
                response.raise_for_status()
                return response.json()
            
        except Exception as e:
            print(f"Error adding movie to Radarr: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"🔍 Response content: {e.response.text}")
            return None
    
    async def get_movie_by_tmdb_id(self, tmdb_id: int) -> Optional[Dict]:
        """Check if movie already exists in Radarr"""
        if not self.base_url:
            print("Radarr error: No URL configured. Please set up Radarr in the Services section.")
            return None
        if not self.api_key:
            print("Radarr error: No API key configured. Please add an API key in the Services section.")
            return None
            
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    f"{self.base_url}/api/v3/movie",
                    headers=self.headers,
                    timeout=10
                )
                response.raise_for_status()
                movies = response.json()
                
                for movie in movies:
                    if movie.get('tmdbId') == tmdb_id:
                        return movie
                return None
            
        except Exception as e:
            print(f"Error checking movie in Radarr: {e}")
            return None
    
    async def get_movie_details(self, radarr_id: int) -> Optional[Dict]:
        """Get detailed movie information from Radarr by internal ID"""
        if not self.base_url:
            print("Radarr error: No URL configured. Please set up Radarr in the Services section.")
            return None
        if not self.api_key:
            print("Radarr error: No API key configured. Please add an API key in the Services section.")
            return None
            
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    f"{self.base_url}/api/v3/movie/{radarr_id}",
                    headers=self.headers,
                    timeout=10
                )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"Error getting movie details from Radarr: {e}")
            return None