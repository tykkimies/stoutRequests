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
        print(f"\n🔍 ===== RADARR SEARCH_MOVIE ===== 🔍")
        print(f"📊 TMDB ID: {tmdb_id}")
        print(f"📊 Base URL: {self.base_url}")
        print(f"📊 API Key Present: {'✅' if self.api_key else '❌'}")
        
        if not self.base_url:
            print("❌ RADARR SEARCH ERROR: No URL configured. Please set up Radarr in the Services section.")
            return None
        if not self.api_key:
            print("❌ RADARR SEARCH ERROR: No API key configured. Please add an API key in the Services section.")
            return None
            
        try:
            search_url = f"{self.base_url}/api/v3/movie/lookup"
            search_params = {'term': f'tmdb:{tmdb_id}'}
            
            print(f"📡 Making GET request to: {search_url}")
            print(f"📡 Search params: {search_params}")
            print(f"📡 Headers: {dict(self.headers)}")
            
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    search_url,
                    headers=self.headers,
                    params=search_params,
                    timeout=10
                )
                
                print(f"📡 Search Response Status: {response.status_code}")
                print(f"📡 Search Response Headers: {dict(response.headers)}")
                
                response.raise_for_status()
                results = response.json()
                
                print(f"📡 Search Results Count: {len(results) if results else 0}")
                if results:
                    first_result = results[0]
                    print(f"✅ MOVIE FOUND: {first_result.get('title', 'Unknown')} ({first_result.get('year', 'Unknown')})")
                    print(f"📊 Title Slug: {first_result.get('titleSlug', 'Unknown')}")
                    print(f"📊 TMDB ID in result: {first_result.get('tmdbId', 'None')}")
                    return first_result
                else:
                    print(f"❌ NO MOVIE FOUND for TMDB ID: {tmdb_id}")
                    return None
                    
        except Exception as e:
            print(f"❌ RADARR SEARCH EXCEPTION: Error searching movie in Radarr: {e}")
            print(f"📊 TMDB ID: {tmdb_id}")
            print(f"📊 URL: {self.base_url}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"📡 HTTP Response Status: {e.response.status_code}")
                print(f"📡 HTTP Response Content: {e.response.text}")
            import traceback
            print(f"🔍 Full stack trace from RadarrService.search_movie:")
            traceback.print_exc()
            return None
    
    async def add_movie(self, tmdb_id: int, quality_profile_id: int = None, root_folder_path: str = None, user_id: int = None, quality_tier: str = None, instance_category: str = None) -> Optional[Dict]:
        """Add movie to Radarr"""
        print(f"\n🎬 ===== RADARR ADD_MOVIE START ===== 🎬")
        print(f"📊 TMDB ID: {tmdb_id}")
        print(f"📊 Quality Profile ID: {quality_profile_id}")
        print(f"📊 Root Folder Path: {root_folder_path}")
        print(f"📊 User ID: {user_id}")
        print(f"📊 Quality Tier: {quality_tier}")
        print(f"📊 Instance Category: {instance_category}")
        print(f"📊 Base URL: {self.base_url}")
        print(f"📊 API Key Present: {'✅' if self.api_key else '❌'}")
        
        if not self.base_url:
            print("❌ RADARR ERROR: No URL configured. Please set up Radarr in the Services section.")
            return None
        if not self.api_key:
            print("❌ RADARR ERROR: No API key configured. Please add an API key in the Services section.")
            return None
            
        try:
            # First search for the movie
            print(f"🔍 Searching for movie with TMDB ID: {tmdb_id}")
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
            
            print(f"🔍 Initial quality_profile_id parameter: {quality_profile_id}")
            
            # Get default settings if not provided
            if not quality_profile_id:
                print("🔍 No quality profile provided, checking user permissions...")
                # First try user permissions
                if user_id:
                    from ..models.user_permissions import UserPermissions
                    from sqlmodel import select
                    user_perms_stmt = select(UserPermissions).where(UserPermissions.user_id == user_id)
                    user_perms = self.session.exec(user_perms_stmt).first()
                    if user_perms and user_perms.movie_quality_profile_id:
                        quality_profile_id = user_perms.movie_quality_profile_id
                        print(f"🔍 Using user permission quality profile: {quality_profile_id}")
                
                # Then try service instance settings
                if not quality_profile_id and self.instance:
                    print("🔍 Checking service instance settings...")
                    settings = self.instance.get_settings()
                    quality_profile_id = settings.get('quality_profile_id')
                    print(f"🔍 Service instance quality profile setting: {quality_profile_id}")
                    print(f"🔍 All service instance settings: {settings}")
                
                # Finally fallback to first available
                if not quality_profile_id:
                    print("🔍 No configured quality profile found, using default...")
                    profiles = await self.get_quality_profiles()
                    if profiles:
                        quality_profile_id = profiles[0]['id']
                        print(f"🔍 Using default quality profile: {profiles[0].get('name', 'Unknown')} (ID: {quality_profile_id})")
                    else:
                        print("❌ No quality profiles available in Radarr")
                        return None
            else:
                print(f"🔍 Using provided quality profile: {quality_profile_id}")
            
            print(f"🔍 Initial root_folder_path parameter: {root_folder_path}")
            
            if not root_folder_path:
                print("🔍 No root folder provided, checking service instance settings...")
                # Try service instance settings first
                if self.instance:
                    settings = self.instance.get_settings()
                    root_folder_path = settings.get('root_folder_path')
                    print(f"🔍 Service instance root folder setting: {root_folder_path}")
                
                # Fallback to first available
                if not root_folder_path:
                    print("🔍 No configured root folder found, using default...")
                    folders = await self.get_root_folders()
                    if folders:
                        root_folder_path = folders[0]['path']
                        print(f"🔍 Using default root folder: {root_folder_path}")
                    else:
                        print("❌ No root folders available in Radarr")
                        return None
            else:
                print(f"🔍 Using provided root folder: {root_folder_path}")
            
            # Get additional settings from service instance
            settings = self.instance.get_settings() if self.instance else {}
            minimum_availability = settings.get('minimum_availability', 'released')
            monitored = settings.get('monitored', True)
            search_for_movie = settings.get('search_for_movie', True)
            print(f"🔍 Radarr search_for_movie setting: {search_for_movie}")
            print(f"🔍 All Radarr settings: {settings}")
            
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
            
            print(f"🔍 Final quality profile ID being sent to Radarr: {quality_profile_id}")
            print(f"🔍 Radarr payload for '{movie_data['title']}': {add_data}")
            
            print(f"📡 Making POST request to Radarr API...")
            print(f"📡 URL: {self.base_url}/api/v3/movie")
            print(f"📡 Headers: {dict(self.headers)}")
            print(f"📡 Payload: {add_data}")
            
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.post(
                    f"{self.base_url}/api/v3/movie",
                    headers=self.headers,
                    json=add_data,
                    timeout=15
                )
                
                print(f"📡 Response Status: {response.status_code}")
                print(f"📡 Response Headers: {dict(response.headers)}")
                
                if not response.is_success:
                    print(f"❌ RADARR API ERROR {response.status_code}: {response.text}")
                    print(f"📡 Request URL: {response.url}")
                    print(f"📡 Request headers: {self.headers}")
                    print(f"📡 Response content type: {response.headers.get('content-type', 'unknown')}")
                    try:
                        error_json = response.json()
                        print(f"📡 Error JSON: {error_json}")
                    except:
                        print(f"📡 Raw error text: {response.text}")
                
                response.raise_for_status()
                response_data = response.json()
                print(f"✅ RADARR ADD_MOVIE SUCCESS: {response_data}")
                return response_data
            
        except Exception as e:
            print(f"❌ RADARR ADD_MOVIE EXCEPTION: Error adding movie to Radarr: {e}")
            print(f"📊 Movie TMDB ID: {tmdb_id}")
            print(f"📊 Instance: {self.instance.name if self.instance else 'Unknown'}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"📡 HTTP Response Status: {e.response.status_code}")
                print(f"📡 HTTP Response Content: {e.response.text}")
                print(f"📡 HTTP Response Headers: {dict(e.response.headers)}")
            import traceback
            print(f"🔍 Full stack trace from RadarrService.add_movie:")
            traceback.print_exc()
            return None
    
    async def get_movie_by_tmdb_id(self, tmdb_id: int) -> Optional[Dict]:
        """Check if movie already exists in Radarr"""
        print(f"\n🔍 ===== RADARR GET_MOVIE_BY_TMDB_ID ===== 🔍")
        print(f"📊 TMDB ID: {tmdb_id}")
        print(f"📊 Base URL: {self.base_url}")
        print(f"📊 API Key Present: {'✅' if self.api_key else '❌'}")
        
        if not self.base_url:
            print("❌ RADARR CHECK ERROR: No URL configured. Please set up Radarr in the Services section.")
            return None
        if not self.api_key:
            print("❌ RADARR CHECK ERROR: No API key configured. Please add an API key in the Services section.")
            return None
            
        try:
            check_url = f"{self.base_url}/api/v3/movie"
            print(f"📡 Making GET request to: {check_url}")
            print(f"📡 Headers: {dict(self.headers)}")
            
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    check_url,
                    headers=self.headers,
                    timeout=10
                )
                
                print(f"📡 Check Response Status: {response.status_code}")
                response.raise_for_status()
                movies = response.json()
                
                print(f"📡 Total movies in Radarr: {len(movies) if movies else 0}")
                
                for movie in movies:
                    if movie.get('tmdbId') == tmdb_id:
                        print(f"✅ MOVIE EXISTS: {movie.get('title', 'Unknown')} (Radarr ID: {movie.get('id', 'Unknown')})")
                        print(f"📊 Status: {movie.get('status', 'Unknown')}")
                        print(f"📊 Monitored: {movie.get('monitored', False)}")
                        return movie
                        
                print(f"⚙️ MOVIE NOT FOUND: TMDB ID {tmdb_id} does not exist in Radarr")
                return None
            
        except Exception as e:
            print(f"❌ RADARR CHECK EXCEPTION: Error checking movie in Radarr: {e}")
            print(f"📊 TMDB ID: {tmdb_id}")
            print(f"📊 URL: {self.base_url}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"📡 HTTP Response Status: {e.response.status_code}")
                print(f"📡 HTTP Response Content: {e.response.text}")
            import traceback
            print(f"🔍 Full stack trace from RadarrService.get_movie_by_tmdb_id:")
            traceback.print_exc()
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