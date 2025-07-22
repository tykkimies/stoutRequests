import httpx
import asyncio
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
    
    async def add_series(self, tmdb_id: int, quality_profile_id: int = None, root_folder_path: str = None, monitor_type: str = 'all', user_id: int = None, season_numbers: Optional[List[int]] = None, episode_numbers: Optional[Dict[int, List[int]]] = None) -> Optional[Dict]:
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
                series_id = existing_series.get('id')
                print(f"⚠️ TV series already exists in Sonarr with ID: {series_id}")
                print(f"🔄 Updating monitoring for existing series: monitor_type={monitor_type}")
                
                # Update monitoring for the existing series with new seasons/episodes
                if monitor_type == 'specificSeasons' and season_numbers:
                    print(f"🔄 Adding season monitoring for seasons: {season_numbers}")
                    updated_series = await self._update_season_monitoring(series_id, season_numbers)
                elif monitor_type == 'specificEpisodes' and episode_numbers:
                    print(f"🔄 Adding episode monitoring for episodes: {episode_numbers}")
                    updated_series = await self._update_episode_monitoring(series_id, episode_numbers)
                else:
                    print(f"🔄 Updating to monitor all seasons")
                    updated_series = await self._update_series_monitoring(series_id, 'all')
                
                if updated_series:
                    print(f"✅ Successfully updated monitoring for existing series: {updated_series.get('title')}")
                    return updated_series
                else:
                    print(f"❌ Failed to update monitoring for existing series")
                    return existing_series  # Return existing data even if update failed
            
            print(f"🔍 Initial Sonarr quality_profile_id parameter: {quality_profile_id}")
            
            # Get default settings if not provided
            if not quality_profile_id:
                print("🔍 No TV quality profile provided, checking user permissions...")
                # First try user permissions
                if user_id:
                    from ..models.user_permissions import UserPermissions
                    from sqlmodel import select
                    user_perms_stmt = select(UserPermissions).where(UserPermissions.user_id == user_id)
                    user_perms = self.session.exec(user_perms_stmt).first()
                    if user_perms and user_perms.tv_quality_profile_id:
                        quality_profile_id = user_perms.tv_quality_profile_id
                        print(f"🔍 Using user permission TV quality profile: {quality_profile_id}")
                
                # Then try service instance settings
                if not quality_profile_id and self.instance:
                    print("🔍 Checking Sonarr service instance settings...")
                    settings = self.instance.get_settings()
                    quality_profile_id = settings.get('quality_profile_id')
                    print(f"🔍 Sonarr service instance quality profile setting: {quality_profile_id}")
                
                # Finally fallback to first available
                if not quality_profile_id:
                    print("🔍 No configured TV quality profile found, using default...")
                    profiles = await self.get_quality_profiles()
                    if profiles:
                        quality_profile_id = profiles[0]['id']
                        print(f"🔍 Using default TV quality profile: {profiles[0].get('name', 'Unknown')} (ID: {quality_profile_id})")
                    else:
                        print("❌ No quality profiles available in Sonarr")
                        return None
            else:
                print(f"🔍 Using provided TV quality profile: {quality_profile_id}")
            
            print(f"🔍 Initial Sonarr root_folder_path parameter: {root_folder_path}")
            
            if not root_folder_path:
                print("🔍 No TV root folder provided, checking service instance settings...")
                # Try service instance settings first
                if self.instance:
                    settings = self.instance.get_settings()
                    root_folder_path = settings.get('root_folder_path')
                    print(f"🔍 Sonarr service instance root folder setting: {root_folder_path}")
                
                # Fallback to first available
                if not root_folder_path:
                    print("🔍 No configured TV root folder found, using default...")
                    folders = await self.get_root_folders()
                    if folders:
                        root_folder_path = folders[0]['path']
                        print(f"🔍 Using default TV root folder: {root_folder_path}")
                    else:
                        print("❌ No root folders available in Sonarr")
                        return None
            else:
                print(f"🔍 Using provided TV root folder: {root_folder_path}")
            
            # Get additional settings from service instance
            settings = self.instance.get_settings() if self.instance else {}
            monitored = settings.get('monitored', True)
            season_folder = settings.get('season_folder', True)
            # Use enable_automatic_search setting for automatic search behavior
            enable_automatic_search = settings.get('enable_automatic_search', True)
            search_for_missing = enable_automatic_search  # Use the automation setting
            language_profile_id = settings.get('language_profile_id', 1)
            print(f"🔍 Sonarr enable_automatic_search setting: {enable_automatic_search}")
            print(f"🔍 Sonarr search_for_missing_episodes setting: {search_for_missing}")
            print(f"🔍 All Sonarr settings: {settings}")
            
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
            if monitor_type == 'specificEpisodes' and episode_numbers:
                add_data['addOptions']['monitor'] = 'none'  # Don't auto-monitor anything
                # We'll need to set up episode monitoring after adding the series
                print(f"🔍 Will monitor specific episodes: {episode_numbers}")
            elif monitor_type == 'specificSeasons' and season_numbers:
                add_data['addOptions']['monitor'] = 'none'  # Don't auto-monitor anything
                # We'll need to set up season monitoring after adding the series
                print(f"🔍 Will monitor specific seasons: {season_numbers}")
            elif monitor_type == 'future':
                add_data['addOptions']['monitor'] = 'future'
            elif monitor_type == 'missing':
                add_data['addOptions']['monitor'] = 'missing'
            elif monitor_type == 'existing':
                add_data['addOptions']['monitor'] = 'existing'
            elif monitor_type == 'all':
                add_data['addOptions']['monitor'] = 'all'
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
                series_result = response.json()
                
                # If this was a specific episode request, configure episode monitoring
                if monitor_type == 'specificEpisodes' and episode_numbers and series_result.get('id'):
                    await self._configure_episode_monitoring(series_result['id'], episode_numbers)
                    # Trigger automatic search if enabled
                    if enable_automatic_search:
                        await self._trigger_episode_search(series_result['id'], episode_numbers)
                # If this was a specific season request, configure season monitoring
                elif monitor_type == 'specificSeasons' and season_numbers and series_result.get('id'):
                    await self._configure_season_monitoring(series_result['id'], season_numbers)
                    # Trigger automatic search if enabled
                    if enable_automatic_search:
                        await self._trigger_season_search(series_result['id'], season_numbers)
                
                return series_result
            
        except Exception as e:
            print(f"Error adding series to Sonarr: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"🔍 Response content: {e.response.text}")
            return None
    
    async def _configure_season_monitoring(self, series_id: int, season_numbers: List[int]):
        """Configure specific season monitoring for a series"""
        try:
            print(f"🔍 Configuring monitoring for seasons {season_numbers} in series {series_id}")
            
            # First, get the series details to understand the season structure
            async with httpx.AsyncClient(follow_redirects=True) as client:
                series_response = await client.get(
                    f"{self.base_url}/api/v3/series/{series_id}",
                    headers=self.headers,
                    timeout=10
                )
                series_response.raise_for_status()
                series_data = series_response.json()
                
                # Update season monitoring
                seasons = series_data.get('seasons', [])
                for season in seasons:
                    season_number = season.get('seasonNumber')
                    if season_number in season_numbers:
                        season['monitored'] = True
                        print(f"✅ Enabled monitoring for season {season_number}")
                    else:
                        season['monitored'] = False
                
                # Update the series with new season monitoring
                update_response = await client.put(
                    f"{self.base_url}/api/v3/series/{series_id}",
                    headers=self.headers,
                    json=series_data,
                    timeout=15
                )
                update_response.raise_for_status()
                print(f"✅ Successfully configured season monitoring for series {series_id}")
                
        except Exception as e:
            print(f"❌ Failed to configure season monitoring: {e}")
            # Don't fail the entire operation if season monitoring fails
    
    async def _configure_episode_monitoring(self, series_id: int, episode_numbers: Dict[int, List[int]]):
        """Configure specific episode monitoring for a series"""
        try:
            print(f"🔍 Configuring monitoring for episodes {episode_numbers} in series {series_id}")
            
            # First, get the series details to understand the season/episode structure
            async with httpx.AsyncClient(follow_redirects=True) as client:
                series_response = await client.get(
                    f"{self.base_url}/api/v3/series/{series_id}",
                    headers=self.headers,
                    timeout=10
                )
                series_response.raise_for_status()
                series_data = series_response.json()
                
                # Turn off monitoring for all seasons initially
                seasons = series_data.get('seasons', [])
                for season in seasons:
                    season['monitored'] = False
                
                # Enable monitoring only for seasons that have requested episodes
                for season_num, episodes in episode_numbers.items():
                    for season in seasons:
                        if season.get('seasonNumber') == season_num:
                            season['monitored'] = True
                            print(f"✅ Enabled monitoring for season {season_num} (contains requested episodes)")
                            break
                
                # Update the series with new season monitoring
                update_response = await client.put(
                    f"{self.base_url}/api/v3/series/{series_id}",
                    headers=self.headers,
                    json=series_data,
                    timeout=15
                )
                update_response.raise_for_status()
                
                # Now configure episode-level monitoring within each season
                for season_num, episodes in episode_numbers.items():
                    print(f"🔍 Configuring episode monitoring for Season {season_num}, Episodes {episodes}")
                    
                    # Get all episodes for this season
                    episodes_response = await client.get(
                        f"{self.base_url}/api/v3/episode?seriesId={series_id}",
                        headers=self.headers,
                        timeout=10
                    )
                    episodes_response.raise_for_status()
                    all_episodes = episodes_response.json()
                    
                    # Filter episodes for this season and update monitoring
                    season_episodes = [ep for ep in all_episodes if ep.get('seasonNumber') == season_num]
                    
                    for episode in season_episodes:
                        episode_num = episode.get('episodeNumber')
                        if episode_num in episodes:
                            episode['monitored'] = True
                            print(f"✅ Enabled monitoring for S{season_num:02d}E{episode_num:02d}")
                        else:
                            episode['monitored'] = False
                    
                    # Update episodes in batch
                    if season_episodes:
                        episodes_update_response = await client.put(
                            f"{self.base_url}/api/v3/episode/monitor",
                            headers=self.headers,
                            json={'episodeIds': [ep['id'] for ep in season_episodes if ep['monitored']]},
                            timeout=15
                        )
                        episodes_update_response.raise_for_status()
                
                print(f"✅ Successfully configured episode monitoring for series {series_id}")
                
        except Exception as e:
            print(f"❌ Failed to configure episode monitoring: {e}")
            # Don't fail the entire operation if episode monitoring fails
    
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
    
    async def _update_season_monitoring(self, series_id: int, season_numbers: List[int]) -> Optional[Dict]:
        """Update monitoring for specific seasons of an existing series"""
        try:
            # Get current series data
            series_data = await self.get_series_details(series_id)
            if not series_data:
                print(f"❌ Could not get series data for ID: {series_id}")
                return None
            
            print(f"🔍 Current series monitoring: {series_data.get('monitored', 'Unknown')}")
            
            # Ensure series is monitored
            series_data['monitored'] = True
            
            # Update season monitoring
            seasons = series_data.get('seasons', [])
            for season in seasons:
                season_num = season.get('seasonNumber')
                if season_num in season_numbers:
                    season['monitored'] = True
                    print(f"🔍 Enabled monitoring for season {season_num}")
            
            # Update the series
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.put(
                    f"{self.base_url}/api/v3/series/{series_id}",
                    headers=self.headers,
                    json=series_data,
                    timeout=30
                )
                response.raise_for_status()
                updated_series = response.json()
                print(f"✅ Updated season monitoring for series: {updated_series.get('title')}")
                return updated_series
                
        except Exception as e:
            print(f"❌ Error updating season monitoring: {e}")
            return None
    
    async def _update_episode_monitoring(self, series_id: int, episode_numbers: Dict[int, List[int]]) -> Optional[Dict]:
        """Update monitoring for specific episodes of an existing series"""
        try:
            # Get current series data
            series_data = await self.get_series_details(series_id)
            if not series_data:
                print(f"❌ Could not get series data for ID: {series_id}")
                return None
            
            # Ensure series is monitored
            series_data['monitored'] = True
            
            # First enable monitoring for seasons that have requested episodes
            seasons = series_data.get('seasons', [])
            for season in seasons:
                season_num = season.get('seasonNumber')
                if season_num in episode_numbers:
                    season['monitored'] = True
                    print(f"🔍 Enabled monitoring for season {season_num} (has requested episodes)")
            
            # Update the series first
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.put(
                    f"{self.base_url}/api/v3/series/{series_id}",
                    headers=self.headers,
                    json=series_data,
                    timeout=30
                )
                response.raise_for_status()
                
                # Now update individual episode monitoring
                for season_num, episodes in episode_numbers.items():
                    try:
                        # Get episodes for this season
                        episodes_response = await client.get(
                            f"{self.base_url}/api/v3/episode",
                            headers=self.headers,
                            params={'seriesId': series_id, 'seasonNumber': season_num},
                            timeout=30
                        )
                        episodes_response.raise_for_status()
                        season_episodes = episodes_response.json()
                        
                        # Update monitoring for specific episodes
                        for episode in season_episodes:
                            episode_num = episode.get('episodeNumber')
                            if episode_num in episodes:
                                episode['monitored'] = True
                                print(f"🔍 Enabling monitoring for S{season_num:02d}E{episode_num:02d}")
                                
                                # Update individual episode
                                episode_response = await client.put(
                                    f"{self.base_url}/api/v3/episode/{episode['id']}",
                                    headers=self.headers,
                                    json=episode,
                                    timeout=10
                                )
                                episode_response.raise_for_status()
                                
                    except Exception as e:
                        print(f"❌ Error updating episode monitoring for season {season_num}: {e}")
                
                # Return updated series data
                updated_response = await client.get(
                    f"{self.base_url}/api/v3/series/{series_id}",
                    headers=self.headers,
                    timeout=10
                )
                updated_response.raise_for_status()
                updated_series = updated_response.json()
                print(f"✅ Updated episode monitoring for series: {updated_series.get('title')}")
                return updated_series
                
        except Exception as e:
            print(f"❌ Error updating episode monitoring: {e}")
            return None
    
    async def _update_series_monitoring(self, series_id: int, monitor_type: str = 'all') -> Optional[Dict]:
        """Update general monitoring for an existing series"""
        try:
            # Get current series data
            series_data = await self.get_series_details(series_id)
            if not series_data:
                print(f"❌ Could not get series data for ID: {series_id}")
                return None
            
            # Enable series monitoring
            series_data['monitored'] = True
            
            # Enable all seasons if monitor_type is 'all'
            if monitor_type == 'all':
                seasons = series_data.get('seasons', [])
                for season in seasons:
                    if season.get('seasonNumber', 0) > 0:  # Skip specials
                        season['monitored'] = True
                        print(f"🔍 Enabled monitoring for season {season.get('seasonNumber')}")
            
            # Update the series
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.put(
                    f"{self.base_url}/api/v3/series/{series_id}",
                    headers=self.headers,
                    json=series_data,
                    timeout=30
                )
                response.raise_for_status()
                updated_series = response.json()
                print(f"✅ Updated series monitoring: {updated_series.get('title')}")
                return updated_series
                
        except Exception as e:
            print(f"❌ Error updating series monitoring: {e}")
            return None
    
    async def _trigger_episode_search(self, series_id: int, episode_numbers: Dict[int, List[int]]):
        """Trigger automatic search for specific episodes"""
        try:
            print(f"🔍 Triggering automatic search for episodes {episode_numbers} in series {series_id}")
            
            async with httpx.AsyncClient(follow_redirects=True) as client:
                # Get all episodes for the series to find episode IDs
                episodes_response = await client.get(
                    f"{self.base_url}/api/v3/episode",
                    headers=self.headers,
                    params={'seriesId': series_id},
                    timeout=30
                )
                episodes_response.raise_for_status()
                all_episodes = episodes_response.json()
                
                # Find episode IDs for the requested episodes
                episode_ids = []
                for season_num, episodes in episode_numbers.items():
                    for episode_num in episodes:
                        for ep in all_episodes:
                            if (ep.get('seasonNumber') == season_num and 
                                ep.get('episodeNumber') == episode_num):
                                episode_ids.append(ep['id'])
                                print(f"🔍 Found episode ID {ep['id']} for S{season_num:02d}E{episode_num:02d} (monitored: {ep.get('monitored', False)})")
                
                if episode_ids:
                    # Trigger search for the specific episodes
                    search_payload = {
                        'name': 'EpisodeSearch',
                        'episodeIds': episode_ids
                    }
                    
                    search_response = await client.post(
                        f"{self.base_url}/api/v3/command",
                        headers=self.headers,
                        json=search_payload,
                        timeout=30
                    )
                    search_response.raise_for_status()
                    search_result = search_response.json()
                    print(f"✅ Successfully triggered automatic search for {len(episode_ids)} episodes")
                    print(f"🔍 Search command ID: {search_result.get('id')}")
                else:
                    print(f"⚠️ No monitored episodes found to search for")
                
        except Exception as e:
            print(f"❌ Failed to trigger episode search: {e}")
            # Don't fail the entire operation if search trigger fails
    
    async def _trigger_season_search(self, series_id: int, season_numbers: List[int]):
        """Trigger automatic search for specific seasons"""
        try:
            print(f"🔍 Triggering automatic search for seasons {season_numbers} in series {series_id}")
            
            async with httpx.AsyncClient(follow_redirects=True) as client:
                for season_num in season_numbers:
                    # Trigger search for the entire season
                    search_payload = {
                        'name': 'SeasonSearch',
                        'seriesId': series_id,
                        'seasonNumber': season_num
                    }
                    
                    search_response = await client.post(
                        f"{self.base_url}/api/v3/command",
                        headers=self.headers,
                        json=search_payload,
                        timeout=30
                    )
                    search_response.raise_for_status()
                    search_result = search_response.json()
                    print(f"✅ Successfully triggered automatic search for season {season_num}")
                    print(f"🔍 Search command ID: {search_result.get('id')}")
                
        except Exception as e:
            print(f"❌ Failed to trigger season search: {e}")
            # Don't fail the entire operation if search trigger fails