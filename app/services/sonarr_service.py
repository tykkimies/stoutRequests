import requests
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
        
        # Get configuration from database
        config = SettingsService.get_sonarr_config(self.session)
        self.base_url = config['url'].rstrip('/') if config['url'] else None
        self.api_key = config['api_key']
        self.headers = {
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        } if self.api_key else {}
    
    def __del__(self):
        if hasattr(self, '_owns_session') and self._owns_session and hasattr(self, 'session'):
            self.session.close()
    
    def test_connection(self) -> bool:
        """Test connection to Sonarr"""
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
            print(f"Sonarr connection test failed: {e}")
            return False
    
    def get_root_folders(self) -> List[Dict]:
        """Get available root folders"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v3/rootfolder",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting Sonarr root folders: {e}")
            return []
    
    def get_quality_profiles(self) -> List[Dict]:
        """Get available quality profiles"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v3/qualityprofile",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting Sonarr quality profiles: {e}")
            return []
    
    def search_series(self, tmdb_id: int) -> Optional[Dict]:
        """Search for TV series by TMDB ID"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v3/series/lookup",
                headers=self.headers,
                params={'term': f'tmdb:{tmdb_id}'}
            )
            response.raise_for_status()
            results = response.json()
            return results[0] if results else None
        except Exception as e:
            print(f"Error searching series in Sonarr: {e}")
            return None
    
    def add_series(self, tmdb_id: int, quality_profile_id: int = None, root_folder_path: str = None, monitor_type: str = 'all') -> Optional[Dict]:
        """Add TV series to Sonarr"""
        try:
            # First search for the series
            series_data = self.search_series(tmdb_id)
            if not series_data:
                return None
            
            # Get default settings if not provided
            if not quality_profile_id:
                profiles = self.get_quality_profiles()
                quality_profile_id = profiles[0]['id'] if profiles else 1
            
            if not root_folder_path:
                folders = self.get_root_folders()
                root_folder_path = folders[0]['path'] if folders else '/tv'
            
            # Prepare series data for adding
            add_data = {
                'title': series_data['title'],
                'qualityProfileId': quality_profile_id,
                'rootFolderPath': root_folder_path,
                'tvdbId': series_data.get('tvdbId', 0),
                'monitored': True,
                'seasonFolder': True,
                'addOptions': {
                    'searchForMissingEpisodes': True,
                    'searchForCutoffUnmetEpisodes': False
                }
            }
            
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
            
            response = requests.post(
                f"{self.base_url}/api/v3/series",
                headers=self.headers,
                json=add_data
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"Error adding series to Sonarr: {e}")
            return None
    
    def get_series_by_tmdb_id(self, tmdb_id: int) -> Optional[Dict]:
        """Check if series already exists in Sonarr"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v3/series",
                headers=self.headers
            )
            response.raise_for_status()
            series_list = response.json()
            
            # Sonarr doesn't always store TMDB ID, so we need to search by title as well
            search_result = self.search_series(tmdb_id)
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