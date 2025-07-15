import requests
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
    
    def test_connection(self) -> bool:
        """Test connection to Radarr"""
        if not self.base_url or not self.api_key:
            return False
            
        try:
            response = requests.get(
                f"{self.base_url}/api/v3/system/status",
                headers=self.headers,
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Radarr connection test failed: {e}")
            return False
    
    def get_root_folders(self) -> List[Dict]:
        """Get available root folders"""
        if not self.base_url or not self.api_key:
            return []
            
        try:
            response = requests.get(
                f"{self.base_url}/api/v3/rootfolder",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting Radarr root folders: {e}")
            return []
    
    def get_quality_profiles(self) -> List[Dict]:
        """Get available quality profiles"""
        if not self.base_url or not self.api_key:
            return []
            
        try:
            response = requests.get(
                f"{self.base_url}/api/v3/qualityprofile",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting Radarr quality profiles: {e}")
            return []
    
    def search_movie(self, tmdb_id: int) -> Optional[Dict]:
        """Search for movie by TMDB ID"""
        if not self.base_url:
            print("Radarr error: No URL configured. Please set up Radarr in the Services section.")
            return None
        if not self.api_key:
            print("Radarr error: No API key configured. Please add an API key in the Services section.")
            return None
            
        try:
            response = requests.get(
                f"{self.base_url}/api/v3/movie/lookup",
                headers=self.headers,
                params={'term': f'tmdb:{tmdb_id}'}
            )
            response.raise_for_status()
            results = response.json()
            return results[0] if results else None
        except Exception as e:
            print(f"Error searching movie in Radarr: {e}")
            return None
    
    def add_movie(self, tmdb_id: int, quality_profile_id: int = None, root_folder_path: str = None) -> Optional[Dict]:
        """Add movie to Radarr"""
        if not self.base_url:
            print("Radarr error: No URL configured. Please set up Radarr in the Services section.")
            return None
        if not self.api_key:
            print("Radarr error: No API key configured. Please add an API key in the Services section.")
            return None
            
        try:
            # First search for the movie
            movie_data = self.search_movie(tmdb_id)
            if not movie_data:
                return None
            
            # Get default settings if not provided
            if not quality_profile_id:
                profiles = self.get_quality_profiles()
                quality_profile_id = profiles[0]['id'] if profiles else 1
            
            if not root_folder_path:
                folders = self.get_root_folders()
                root_folder_path = folders[0]['path'] if folders else '/movies'
            
            # Prepare movie data for adding
            add_data = {
                'title': movie_data['title'],
                'qualityProfileId': quality_profile_id,
                'rootFolderPath': root_folder_path,
                'tmdbId': tmdb_id,
                'monitored': True,
                'minimumAvailability': 'released',
                'addOptions': {
                    'searchForMovie': True
                }
            }
            
            # Add any additional fields from the search result
            for field in ['year', 'images', 'runtime', 'overview']:
                if field in movie_data:
                    add_data[field] = movie_data[field]
            
            response = requests.post(
                f"{self.base_url}/api/v3/movie",
                headers=self.headers,
                json=add_data
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"Error adding movie to Radarr: {e}")
            return None
    
    def get_movie_by_tmdb_id(self, tmdb_id: int) -> Optional[Dict]:
        """Check if movie already exists in Radarr"""
        if not self.base_url:
            print("Radarr error: No URL configured. Please set up Radarr in the Services section.")
            return None
        if not self.api_key:
            print("Radarr error: No API key configured. Please add an API key in the Services section.")
            return None
            
        try:
            response = requests.get(
                f"{self.base_url}/api/v3/movie",
                headers=self.headers
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
    
    def get_movie_details(self, radarr_id: int) -> Optional[Dict]:
        """Get detailed movie information from Radarr by internal ID"""
        if not self.base_url:
            print("Radarr error: No URL configured. Please set up Radarr in the Services section.")
            return None
        if not self.api_key:
            print("Radarr error: No API key configured. Please add an API key in the Services section.")
            return None
            
        try:
            response = requests.get(
                f"{self.base_url}/api/v3/movie/{radarr_id}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"Error getting movie details from Radarr: {e}")
            return None