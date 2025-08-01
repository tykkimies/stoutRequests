import requests
from typing import Dict, Optional
from sqlmodel import Session
from datetime import datetime, timedelta

from ..services.settings_service import SettingsService


class TMDBService:
    # Default TMDB API key (like Ombi uses) - allows app to work out of the box
    DEFAULT_API_KEY = "b8eabaf5608b88d0298aa189dd90bf00"
    
    def __init__(self, session: Session = None):
        if session is None:
            # Create a new session if none provided
            from ..core.database import engine
            self.session = Session(engine)
            self._owns_session = True
        else:
            self.session = session
            self._owns_session = False
        
        # Get configuration from database, fallback to default key
        config = SettingsService.get_tmdb_config(self.session)
        self.api_key = config['api_key'] or self.DEFAULT_API_KEY
        self.base_url = "https://api.themoviedb.org/3"
        self.image_base_url = "https://image.tmdb.org/t/p/w500"
        
        # Unified category mapping system
        self.category_mappings = {
            'movie': {
                'popular': {
                    'use_discover': True,
                    'sort_by': 'popularity.desc',
                    'additional_params': {}
                },
                'top_rated': {
                    'use_discover': True,
                    'sort_by': 'vote_average.desc',
                    'additional_params': {
                        'vote_count_gte': 200  # Ensure enough votes for meaningful rating
                    }
                },
                'trending': {
                    'use_discover': False,  # Uses trending endpoint - no discover equivalent
                    'endpoint': 'trending'
                },
                'upcoming': {
                    'use_discover': True,
                    'sort_by': 'primary_release_date.desc',
                    'additional_params': {
                        'primary_release_date.gte': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
                        'primary_release_date.lte': (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
                    }
                },
                'now_playing': {
                    'use_discover': True,
                    'sort_by': 'popularity.desc',
                    'additional_params': {
                        'primary_release_date.gte': (datetime.now() - timedelta(days=45)).strftime('%Y-%m-%d'),
                        'primary_release_date.lte': datetime.now().strftime('%Y-%m-%d')
                    }
                }
            },
            'tv': {
                'popular': {
                    'use_discover': True,
                    'sort_by': 'popularity.desc',
                    'additional_params': {}
                },
                'top_rated': {
                    'use_discover': True,
                    'sort_by': 'vote_average.desc',
                    'additional_params': {
                        'vote_count_gte': 200  # Ensure enough votes for meaningful rating
                    }
                },
                'trending': {
                    'use_discover': False,  # Uses trending endpoint - no discover equivalent
                    'endpoint': 'trending'
                }
            }
        }
    
    def __del__(self):
        if hasattr(self, '_owns_session') and self._owns_session and hasattr(self, 'session'):
            self.session.close()
    
    def search_multi(self, query: str, page: int = 1) -> Dict:
        """Search for movies and TV shows"""
        url = f"{self.base_url}/search/multi"
        params = {
            'api_key': self.api_key,
            'query': query,
            'page': page,
            'include_adult': False
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        # Process results to add full image URLs
        self._process_results(data.get('results', []))
        
        return data
    
    def get_movie_details(self, movie_id: int) -> Dict:
        """Get detailed movie information"""
        url = f"{self.base_url}/movie/{movie_id}"
        params = {'api_key': self.api_key}
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()
    
    def get_tv_details(self, tv_id: int) -> Dict:
        """Get detailed TV show information"""
        url = f"{self.base_url}/tv/{tv_id}"
        params = {'api_key': self.api_key}
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()
    
    def get_movie_credits(self, movie_id: int) -> Dict:
        """Get movie cast and crew information"""
        url = f"{self.base_url}/movie/{movie_id}/credits"
        params = {'api_key': self.api_key}
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()
    
    def get_tv_credits(self, tv_id: int) -> Dict:
        """Get TV show cast and crew information"""
        url = f"{self.base_url}/tv/{tv_id}/credits"
        params = {'api_key': self.api_key}
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()
    
    def get_trending(self, media_type: str, page: int = 1) -> Dict:
        """Get trending movies or TV shows (no filter support)"""
        url = f"{self.base_url}/trending/{media_type}/week"
        params = {
            'api_key': self.api_key,
            'page': page
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        self._process_results(data.get('results', []))
        return data
    
    def get_popular(self, media_type: str, page: int = 1) -> Dict:
        """Get popular movies or TV shows"""
        endpoint = "movie" if media_type == "movie" else "tv"
        url = f"{self.base_url}/{endpoint}/popular"
        params = {
            'api_key': self.api_key,
            'page': page
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        self._process_results(data.get('results', []))
        return data
    
    def get_top_rated(self, media_type: str, page: int = 1) -> Dict:
        """Get top rated movies or TV shows"""
        endpoint = "movie" if media_type == "movie" else "tv"
        url = f"{self.base_url}/{endpoint}/top_rated"
        params = {
            'api_key': self.api_key,
            'page': page
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        self._process_results(data.get('results', []))
        return data
    
    def get_upcoming_movies(self, page: int = 1) -> Dict:
        """Get upcoming movies"""
        url = f"{self.base_url}/movie/upcoming"
        params = {
            'api_key': self.api_key,
            'page': page
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        self._process_results(data.get('results', []))
        return data
    
    def get_now_playing_movies(self, page: int = 1) -> Dict:
        """Get now playing movies"""
        url = f"{self.base_url}/movie/now_playing"
        params = {
            'api_key': self.api_key,
            'page': page
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        self._process_results(data.get('results', []))
        return data
    
    def _process_results(self, results: list):
        """Process results to add full image URLs"""
        for result in results:
            if result.get('poster_path'):
                result['poster_url'] = f"{self.image_base_url}{result['poster_path']}"
            else:
                result['poster_url'] = None
                
            if result.get('backdrop_path'):
                result['backdrop_url'] = f"{self.image_base_url}{result['backdrop_path']}"
            else:
                result['backdrop_url'] = None
    
    def get_details(self, item_id: int, media_type: str) -> Dict:
        """Get detailed information for a movie or TV show"""
        if media_type == "movie":
            return self.get_movie_details(item_id)
        elif media_type == "tv":
            return self.get_tv_details(item_id)
        elif media_type == "mixed":
            # For mixed media type in details, we need to determine what type this specific item is
            # Try movie first, then TV if that fails
            try:
                return self.get_movie_details(item_id)
            except:
                try:
                    return self.get_tv_details(item_id)
                except:
                    raise ValueError(f"Could not fetch details for item {item_id} as either movie or TV show")
        else:
            raise ValueError(f"Invalid media_type: {media_type}")
    
    def get_watch_providers(self, item_id: int, media_type: str) -> Dict:
        """Get watch providers (streaming services) for a movie or TV show"""
        if media_type == "mixed":
            # For mixed media type, try to determine what type this specific item is
            # Try movie first, then TV if that fails
            try:
                url = f"{self.base_url}/movie/{item_id}/watch/providers"
                params = {'api_key': self.api_key}
                response = requests.get(url, params=params)
                response.raise_for_status()
                return response.json()
            except:
                try:
                    url = f"{self.base_url}/tv/{item_id}/watch/providers"
                    params = {'api_key': self.api_key}
                    response = requests.get(url, params=params)
                    response.raise_for_status()
                    return response.json()
                except:
                    # Return empty providers if both fail
                    return {'results': {}}
        
        url = f"{self.base_url}/{media_type}/{item_id}/watch/providers"
        params = {
            'api_key': self.api_key
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()
    
    def get_movie_similar(self, movie_id: int, page: int = 1) -> Dict:
        """Get similar movies"""
        url = f"{self.base_url}/movie/{movie_id}/similar"
        params = {
            'api_key': self.api_key,
            'page': page
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        self._process_results(data.get('results', []))
        return data
    
    def get_movie_recommendations(self, movie_id: int, page: int = 1) -> Dict:
        """Get movie recommendations"""
        url = f"{self.base_url}/movie/{movie_id}/recommendations"
        params = {
            'api_key': self.api_key,
            'page': page
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        self._process_results(data.get('results', []))
        return data
    
    def get_tv_similar(self, tv_id: int, page: int = 1) -> Dict:
        """Get similar TV shows"""
        url = f"{self.base_url}/tv/{tv_id}/similar"
        params = {
            'api_key': self.api_key,
            'page': page
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        self._process_results(data.get('results', []))
        return data
    
    def get_tv_recommendations(self, tv_id: int, page: int = 1) -> Dict:
        """Get TV show recommendations"""
        url = f"{self.base_url}/tv/{tv_id}/recommendations"
        params = {
            'api_key': self.api_key,
            'page': page
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        self._process_results(data.get('results', []))
        return data
    
    def get_person_details(self, person_id: int) -> Dict:
        """Get person details"""
        url = f"{self.base_url}/person/{person_id}"
        params = {'api_key': self.api_key}
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()
    
    def get_person_movie_credits(self, person_id: int) -> Dict:
        """Get person's movie credits"""
        url = f"{self.base_url}/person/{person_id}/movie_credits"
        params = {'api_key': self.api_key}
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        # Process cast and crew results
        if 'cast' in data:
            self._process_results(data['cast'])
        if 'crew' in data:
            self._process_results(data['crew'])
        return data
    
    def get_person_tv_credits(self, person_id: int) -> Dict:
        """Get person's TV credits"""
        url = f"{self.base_url}/person/{person_id}/tv_credits"
        params = {'api_key': self.api_key}
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        # Process cast and crew results
        if 'cast' in data:
            self._process_results(data['cast'])
        if 'crew' in data:
            self._process_results(data['crew'])
        return data
    
    def get_media_videos(self, item_id: int, media_type: str) -> Dict:
        """Get videos (trailers) for media from TMDB"""
        if media_type not in ['movie', 'tv']:
            return {}
            
        url = f"{self.base_url}/{media_type}/{item_id}/videos"
        params = {'api_key': self.api_key}
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            videos = data.get('results', [])
            
            # Filter for YouTube trailers, prioritize official trailers
            trailers = []
            for video in videos:
                if video.get('site') == 'YouTube' and video.get('type') in ['Trailer', 'Teaser']:
                    trailers.append(video)
            
            # Sort by priority: Official Trailer > Trailer > Teaser
            def trailer_priority(video):
                name = video.get('name', '').lower()
                if 'official trailer' in name:
                    return 0
                elif video.get('type') == 'Trailer':
                    return 1
                elif video.get('type') == 'Teaser':
                    return 2
                return 3
            
            trailers.sort(key=trailer_priority)
            
            return {
                'results': trailers,
                'total_results': len(trailers)
            }
            
        except Exception as e:
            print(f"Error fetching videos for {media_type} {item_id}: {e}")
            return {'results': [], 'total_results': 0}
    
    def discover_movies_by_person(self, person_id: int, page: int = 1) -> Dict:
        """Discover movies by person"""
        url = f"{self.base_url}/discover/movie"
        params = {
            'api_key': self.api_key,
            'with_cast': person_id,
            'page': page,
            'sort_by': 'popularity.desc'
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        self._process_results(data.get('results', []))
        return data
    
    def discover_tv_by_person(self, person_id: int, page: int = 1) -> Dict:
        """Discover TV shows by person"""
        url = f"{self.base_url}/discover/tv"
        params = {
            'api_key': self.api_key,
            'with_cast': person_id,
            'page': page,
            'sort_by': 'popularity.desc'
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        self._process_results(data.get('results', []))
        return data
    
    def discover_movies(self, page: int = 1, sort_by: str = 'popularity.desc', 
                       with_genres: str = None, vote_average_gte: float = None,
                       vote_count_gte: int = None,
                       with_companies: str = None, with_watch_providers: str = None,
                       primary_release_date_gte: str = None, primary_release_date_lte: str = None,
                       region: str = "US", watch_region: str = "US") -> Dict:
        """Discover movies with flexible filtering and sorting"""
        url = f"{self.base_url}/discover/movie"
        params = {
            'api_key': self.api_key,
            'page': page,
            'sort_by': sort_by,
            'region': region
        }
        
        # Add optional filters
        if with_genres:
            params['with_genres'] = with_genres
        if vote_average_gte:
            params['vote_average.gte'] = vote_average_gte
        if vote_count_gte:
            params['vote_count.gte'] = vote_count_gte
        if with_companies:
            params['with_companies'] = with_companies
        if with_watch_providers:
            params['with_watch_providers'] = with_watch_providers
            # CRITICAL FIX: watch_region is REQUIRED when using with_watch_providers
            params['watch_region'] = watch_region
        if primary_release_date_gte:
            # Handle both string and int formats
            if isinstance(primary_release_date_gte, int):
                params['primary_release_date.gte'] = f"{primary_release_date_gte}-01-01"
            else:
                params['primary_release_date.gte'] = primary_release_date_gte
        if primary_release_date_lte:
            # Handle both string and int formats
            if isinstance(primary_release_date_lte, int):
                params['primary_release_date.lte'] = f"{primary_release_date_lte}-12-31"
            else:
                params['primary_release_date.lte'] = primary_release_date_lte
        
        # Debug logging for TMDB API calls
        print(f"🌐 TMDB Movies API Request URL: {url}")
        print(f"🌐 TMDB Movies API Parameters: {params}")
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        print(f"🌐 TMDB Movies API Response: {len(data.get('results', []))} results found")
        
        # Debug the actual ratings returned
        if data.get('results'):
            ratings = [result.get('vote_average', 0) for result in data.get('results', [])]
            print(f"🌐 TMDB Movies API Ratings: {ratings}")
            print(f"🌐 Min rating in results: {min(ratings) if ratings else 'N/A'}")
            print(f"🌐 Max rating in results: {max(ratings) if ratings else 'N/A'}")
        
        self._process_results(data.get('results', []))
        return data
    
    def discover_tv(self, page: int = 1, sort_by: str = 'popularity.desc',
                   with_genres: str = None, vote_average_gte: float = None,
                   vote_count_gte: int = None,
                   with_networks: str = None, with_companies: str = None, with_watch_providers: str = None,
                   first_air_date_gte: str = None, first_air_date_lte: str = None,
                   region: str = "US", watch_region: str = "US") -> Dict:
        """Discover TV shows with flexible filtering and sorting"""
        url = f"{self.base_url}/discover/tv"
        params = {
            'api_key': self.api_key,
            'page': page,
            'sort_by': sort_by,
            'region': region
        }
        
        # Add optional filters
        if with_genres:
            params['with_genres'] = with_genres
        if vote_average_gte:
            params['vote_average.gte'] = vote_average_gte
        if vote_count_gte:
            params['vote_count.gte'] = vote_count_gte
        if with_networks:
            params['with_networks'] = with_networks
        if with_companies:
            params['with_companies'] = with_companies
        if with_watch_providers:
            params['with_watch_providers'] = with_watch_providers
            # CRITICAL FIX: watch_region is REQUIRED when using with_watch_providers
            params['watch_region'] = watch_region
        if first_air_date_gte:
            # Handle both string and int formats
            if isinstance(first_air_date_gte, int):
                params['first_air_date.gte'] = f"{first_air_date_gte}-01-01"
            else:
                params['first_air_date.gte'] = first_air_date_gte
        if first_air_date_lte:
            # Handle both string and int formats
            if isinstance(first_air_date_lte, int):
                params['first_air_date.lte'] = f"{first_air_date_lte}-12-31"
            else:
                params['first_air_date.lte'] = first_air_date_lte
        
        # Debug logging for TMDB API calls
        print(f"🌐 TMDB TV API Request URL: {url}")
        print(f"🌐 TMDB TV API Parameters: {params}")
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        print(f"🌐 TMDB TV API Response: {len(data.get('results', []))} results found")
        
        # Debug the actual ratings returned
        if data.get('results'):
            ratings = [result.get('vote_average', 0) for result in data.get('results', [])]
            print(f"🌐 TMDB TV API Ratings: {ratings}")
            print(f"🌐 Min rating in results: {min(ratings) if ratings else 'N/A'}")
            print(f"🌐 Max rating in results: {max(ratings) if ratings else 'N/A'}")
        
        self._process_results(data.get('results', []))
        return data
    
    def get_genre_list(self, media_type: str = 'movie') -> Dict:
        """Get the official list of genres for movies or TV shows"""
        url = f"{self.base_url}/genre/{media_type}/list"
        params = {'api_key': self.api_key}
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()
    
    def get_tv_season_details(self, tv_id: int, season_number: int) -> Dict:
        """Get detailed information about a specific TV season"""
        url = f"{self.base_url}/tv/{tv_id}/season/{season_number}"
        params = {'api_key': self.api_key}
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()
    
    def get_category_content(self, media_type: str, category: str, page: int = 1, 
                           with_genres: str = None, vote_average_gte: float = None,
                           with_companies: str = None, with_networks: str = None,
                           with_watch_providers: str = None,
                           primary_release_date_gte: str = None, primary_release_date_lte: str = None,
                           first_air_date_gte: str = None, first_air_date_lte: str = None,
                           region: str = "US") -> Dict:
        """
        Unified method to get category content consistently for both horizontal scroll and expanded views.
        Maps category names to appropriate TMDB API calls with consistent parameters.
        """
        # Handle mixed media type by combining movie and TV results
        if media_type == "mixed":
            return self._get_mixed_content(
                category, page, with_genres, vote_average_gte, with_companies, 
                with_networks, with_watch_providers, primary_release_date_gte, 
                primary_release_date_lte, first_air_date_gte, first_air_date_lte, region
            )
        
        # Get category mapping
        if media_type not in self.category_mappings:
            raise ValueError(f"Invalid media_type: {media_type}")
        
        if category not in self.category_mappings[media_type]:
            raise ValueError(f"Invalid category '{category}' for media_type '{media_type}'")
        
        category_config = self.category_mappings[media_type][category]
        
        # Handle trending with filter support
        if not category_config['use_discover']:
            if category_config['endpoint'] == 'trending':
                # Check if any filters are applied
                has_filters = any([
                    with_genres, vote_average_gte, with_companies, with_networks,
                    with_watch_providers, primary_release_date_gte, primary_release_date_lte,
                    first_air_date_gte, first_air_date_lte
                ])
                
                if has_filters:
                    # Use discover API with popularity sort to simulate trending behavior with filters
                    if media_type == 'movie':
                        return self.discover_movies(
                            page=page,
                            sort_by='popularity.desc',  # Most similar to trending
                            with_genres=with_genres,
                            vote_average_gte=vote_average_gte,
                            with_companies=with_companies,
                            with_watch_providers=with_watch_providers,
                            primary_release_date_gte=primary_release_date_gte,
                            primary_release_date_lte=primary_release_date_lte,
                            region=region,
                            watch_region=region
                        )
                    else:  # tv
                        return self.discover_tv(
                            page=page,
                            sort_by='popularity.desc',  # Most similar to trending
                            with_genres=with_genres,
                            vote_average_gte=vote_average_gte,
                            with_networks=with_networks,
                            with_companies=with_companies,
                            with_watch_providers=with_watch_providers,
                            first_air_date_gte=first_air_date_gte,
                            first_air_date_lte=first_air_date_lte,
                            region=region,
                            watch_region=region
                        )
                else:
                    # No filters applied, use original trending endpoint for authentic results
                    return self.get_trending(media_type, page)
        
        # Use discover API for consistent filtering and sorting
        if media_type == 'movie':
            # Build parameters for movie discovery
            params = {
                'page': page,
                'sort_by': category_config['sort_by'],
                'region': region
            }
            
            # Add category-specific parameters (convert dot notation to underscore notation)
            for key, value in category_config['additional_params'].items():
                # Convert TMDB API parameter names (with dots) to method parameter names (with underscores)
                param_key = key.replace('.', '_')
                params[param_key] = value
            
            # Add user filter parameters if provided
            if with_genres:
                params['with_genres'] = with_genres
            if vote_average_gte:
                params['vote_average_gte'] = vote_average_gte
            if with_companies:
                params['with_companies'] = with_companies
            if with_watch_providers:
                params['with_watch_providers'] = with_watch_providers
            if primary_release_date_gte:
                params['primary_release_date_gte'] = primary_release_date_gte
            if primary_release_date_lte:
                params['primary_release_date_lte'] = primary_release_date_lte
            
            # Add watch_region parameter for streaming filters
            if with_watch_providers:
                params['watch_region'] = region
            return self.discover_movies(**params)
            
        elif media_type == 'tv':
            # Build parameters for TV discovery
            params = {
                'page': page,
                'sort_by': category_config['sort_by'],
                'region': region
            }
            
            # Add category-specific parameters (convert dot notation to underscore notation)
            for key, value in category_config['additional_params'].items():
                # Convert TMDB API parameter names (with dots) to method parameter names (with underscores)
                param_key = key.replace('.', '_')
                params[param_key] = value
            
            # Add user filter parameters if provided
            if with_genres:
                params['with_genres'] = with_genres
            if vote_average_gte:
                params['vote_average_gte'] = vote_average_gte
            if with_companies:
                params['with_companies'] = with_companies
            if with_networks:
                params['with_networks'] = with_networks
            if with_watch_providers:
                params['with_watch_providers'] = with_watch_providers
            if first_air_date_gte:
                params['first_air_date_gte'] = first_air_date_gte
            if first_air_date_lte:
                params['first_air_date_lte'] = first_air_date_lte
            
            # Add watch_region parameter for streaming filters
            if with_watch_providers:
                params['watch_region'] = region
            return self.discover_tv(**params)
    
    def _get_mixed_content(self, category: str, page: int = 1, 
                          with_genres: str = None, vote_average_gte: float = None,
                          with_companies: str = None, with_networks: str = None,
                          with_watch_providers: str = None,
                          primary_release_date_gte: str = None, primary_release_date_lte: str = None,
                          first_air_date_gte: str = None, first_air_date_lte: str = None,
                          region: str = "US") -> Dict:
        """
        Get mixed content by combining movie and TV results.
        Makes separate API calls for movies and TV shows, then combines and sorts the results.
        CRITICAL FIX: Properly maps date parameters between movie and TV API calls.
        """
        try:
            # Ensure both media types support this category
            if category not in self.category_mappings.get('movie', {}):
                raise ValueError(f"Category '{category}' not supported for movies")
            if category not in self.category_mappings.get('tv', {}):
                raise ValueError(f"Category '{category}' not supported for TV shows")
            
            # Handle genre mapping for mixed content
            movie_genres = with_genres
            tv_genres = with_genres
            
            if with_genres:
                # Map genres to appropriate IDs for each media type
                movie_genres, tv_genres = self._map_genres_for_mixed_content(with_genres)
            
            # CRITICAL FIX: Map date parameters correctly between movie and TV
            # If we have movie date parameters but not TV date parameters, map them
            tv_first_air_date_gte = first_air_date_gte
            tv_first_air_date_lte = first_air_date_lte
            
            # Map movie date filters to TV date filters if TV dates not provided
            if primary_release_date_gte and not first_air_date_gte:
                tv_first_air_date_gte = primary_release_date_gte
            if primary_release_date_lte and not first_air_date_lte:
                tv_first_air_date_lte = primary_release_date_lte
                
            # Similarly, map TV date filters to movie date filters if needed
            movie_primary_release_date_gte = primary_release_date_gte
            movie_primary_release_date_lte = primary_release_date_lte
            
            if first_air_date_gte and not primary_release_date_gte:
                movie_primary_release_date_gte = first_air_date_gte
            if first_air_date_lte and not primary_release_date_lte:
                movie_primary_release_date_lte = first_air_date_lte
            
            print(f"🔍 MIXED CONTENT DEBUG - Movie dates: {movie_primary_release_date_gte} to {movie_primary_release_date_lte}")
            print(f"🔍 MIXED CONTENT DEBUG - TV dates: {tv_first_air_date_gte} to {tv_first_air_date_lte}")
            
            # Calculate pages for each media type to get roughly equal representation
            # For page 1, get 10 items from each. For page 2+, alternate or split accordingly
            items_per_type = 10  # 10 movies + 10 TV shows = 20 total per page
            
            # Get movie results
            try:
                movie_results = self.get_category_content(
                    "movie", category, page=page,
                    with_genres=movie_genres, vote_average_gte=vote_average_gte,
                    with_companies=with_companies, with_watch_providers=with_watch_providers,
                    primary_release_date_gte=movie_primary_release_date_gte, 
                    primary_release_date_lte=movie_primary_release_date_lte,
                    region=region
                )
                movies = movie_results.get('results', [])
                # Ensure each movie has media_type set
                for movie in movies:
                    movie['media_type'] = 'movie'
            except Exception as e:
                print(f"Error fetching movies for mixed content: {e}")
                movies = []
            
            # Get TV results
            try:
                tv_results = self.get_category_content(
                    "tv", category, page=page,
                    with_genres=tv_genres, vote_average_gte=vote_average_gte,
                    with_companies=with_companies, with_networks=with_networks,
                    with_watch_providers=with_watch_providers,
                    first_air_date_gte=tv_first_air_date_gte,
                    first_air_date_lte=tv_first_air_date_lte,
                    region=region
                )
                tv_shows = tv_results.get('results', [])
                # Ensure each TV show has media_type set
                for show in tv_shows:
                    show['media_type'] = 'tv'
            except Exception as e:
                print(f"Error fetching TV shows for mixed content: {e}")
                tv_shows = []
            
            # Combine results
            combined_results = []
            
            # Take up to items_per_type from each, interleaving them
            max_items = max(len(movies), len(tv_shows))
            for i in range(max_items):
                if i < len(movies):
                    combined_results.append(movies[i])
                if i < len(tv_shows):
                    combined_results.append(tv_shows[i])
                    
                # Stop when we have enough items for this page
                if len(combined_results) >= 20:
                    break
            
            # Sort combined results by popularity (descending) for better mixing
            def get_popularity(item):
                return item.get('popularity', 0)
            
            combined_results.sort(key=get_popularity, reverse=True)
            
            # Calculate total pages based on the maximum of the two result sets
            movie_total_pages = movie_results.get('total_pages', 1) if movies else 1
            tv_total_pages = tv_results.get('total_pages', 1) if tv_shows else 1
            max_total_pages = max(movie_total_pages, tv_total_pages)
            
            # Calculate total results 
            movie_total_results = movie_results.get('total_results', 0) if movies else 0
            tv_total_results = tv_results.get('total_results', 0) if tv_shows else 0
            total_results = movie_total_results + tv_total_results
            
            return {
                'results': combined_results,
                'page': page,
                'total_pages': max_total_pages,
                'total_results': total_results
            }
            
        except Exception as e:
            print(f"Error in _get_mixed_content: {e}")
            # Return empty results on error
            return {
                'results': [],
                'page': page,
                'total_pages': 1,
                'total_results': 0
            }
    
    def _map_genres_for_mixed_content(self, genre_ids_str: str):
        """
        Map genre IDs appropriately for mixed content queries.
        CRITICAL FIX: Direct ID mapping based on comprehensive TMDB research.
        Some genres have completely different IDs between movies and TV shows.
        
        Based on research findings:
        - Action: Movie ID 28 → TV ID 10759 (Action & Adventure)
        - Adventure: Movie ID 12 → TV ID 10759 (Action & Adventure) 
        - Fantasy: Movie ID 14 → TV ID 10765 (Sci-Fi & Fantasy)
        - Science Fiction: Movie ID 878 → TV ID 10765 (Sci-Fi & Fantasy)
        - War: Movie ID 10752 → TV ID 10768 (War & Politics)
        """
        if not genre_ids_str:
            return None, None
            
        try:
            print(f"🔄 Genre mapping DEBUG: Starting with input genres: {genre_ids_str}")
            
            # Complete Movie Genre List (19 genres)
            movie_genres = {
                '28': 'Action',
                '12': 'Adventure', 
                '16': 'Animation',
                '35': 'Comedy',
                '80': 'Crime',
                '99': 'Documentary',
                '18': 'Drama',
                '10751': 'Family',
                '14': 'Fantasy',
                '36': 'History',
                '27': 'Horror',
                '10402': 'Music',
                '9648': 'Mystery',
                '10749': 'Romance',
                '878': 'Science Fiction',
                '10770': 'TV Movie',
                '53': 'Thriller',
                '10752': 'War',
                '37': 'Western'
            }
            
            # Complete TV Genre List (16 genres)
            tv_genres = {
                '10759': 'Action & Adventure',
                '16': 'Animation',
                '35': 'Comedy',
                '80': 'Crime',
                '99': 'Documentary',
                '18': 'Drama',
                '10751': 'Family',
                '10762': 'Kids',
                '9648': 'Mystery',
                '10763': 'News',
                '10764': 'Reality',
                '10765': 'Sci-Fi & Fantasy',
                '10766': 'Soap',
                '10767': 'Talk',
                '10768': 'War & Politics',
                '37': 'Western'
            }
            
            # Direct ID Mapping: Movie ID → TV ID
            movie_to_tv_mapping = {
                '28': '10759',    # Action → Action & Adventure
                '12': '10759',    # Adventure → Action & Adventure
                '14': '10765',    # Fantasy → Sci-Fi & Fantasy
                '878': '10765',   # Science Fiction → Sci-Fi & Fantasy
                '10752': '10768', # War → War & Politics
                # Direct matches (same ID)
                '16': '16',       # Animation
                '35': '35',       # Comedy
                '80': '80',       # Crime
                '99': '99',       # Documentary
                '18': '18',       # Drama
                '10751': '10751', # Family
                '9648': '9648',   # Mystery
                '37': '37'        # Western
            }
            
            # Direct ID Mapping: TV ID → Movie ID
            tv_to_movie_mapping = {
                '10759': '28',    # Action & Adventure → Action (primary mapping)
                '10765': '878',   # Sci-Fi & Fantasy → Science Fiction (primary mapping)
                '10768': '10752', # War & Politics → War
                # Direct matches (same ID)
                '16': '16',       # Animation
                '35': '35',       # Comedy
                '80': '80',       # Crime
                '99': '99',       # Documentary
                '18': '18',       # Drama
                '10751': '10751', # Family
                '9648': '9648',   # Mystery
                '37': '37'        # Western
            }
            
            # Movie-only genres (exclude from TV)
            movie_only_genres = {'10402', '10749', '53', '10770', '36', '27'}  # Music, Romance, Thriller, TV Movie, History, Horror
            
            # TV-only genres (exclude from movies)
            tv_only_genres = {'10762', '10763', '10764', '10766', '10767'}  # Kids, News, Reality, Soap, Talk
            
            # Parse the input genre IDs
            input_genre_ids = [id.strip() for id in genre_ids_str.split(',') if id.strip()]
            
            movie_mapped_ids = []
            tv_mapped_ids = []
            
            for genre_id in input_genre_ids:
                print(f"🔄 Processing genre ID: {genre_id}")
                
                # Determine if this is a movie genre, TV genre, or both
                is_movie_genre = genre_id in movie_genres
                is_tv_genre = genre_id in tv_genres
                
                # Handle movie mapping
                if is_movie_genre:
                    # Always add movie genre for movie results
                    movie_mapped_ids.append(genre_id)
                    print(f"🔄 Added movie genre: {genre_id} ({movie_genres[genre_id]})")
                elif is_tv_genre and genre_id in tv_to_movie_mapping:
                    # Map TV genre to movie equivalent
                    mapped_movie_id = tv_to_movie_mapping[genre_id]
                    movie_mapped_ids.append(mapped_movie_id)
                    print(f"🔄 Mapped TV genre {genre_id} ({tv_genres[genre_id]}) to movie genre {mapped_movie_id} ({movie_genres[mapped_movie_id]})")
                
                # Handle TV mapping
                if is_tv_genre:
                    # Always add TV genre for TV results
                    tv_mapped_ids.append(genre_id)
                    print(f"🔄 Added TV genre: {genre_id} ({tv_genres[genre_id]})")
                elif is_movie_genre and genre_id in movie_to_tv_mapping:
                    # Map movie genre to TV equivalent (but only if it's not movie-only)
                    if genre_id not in movie_only_genres:
                        mapped_tv_id = movie_to_tv_mapping[genre_id]
                        tv_mapped_ids.append(mapped_tv_id)
                        print(f"🔄 Mapped movie genre {genre_id} ({movie_genres[genre_id]}) to TV genre {mapped_tv_id} ({tv_genres[mapped_tv_id]})")
                    else:
                        print(f"🔄 Skipping movie-only genre {genre_id} ({movie_genres[genre_id]}) for TV mapping")
                
                # Handle unknown genres (shouldn't happen with valid TMDB data)
                if not is_movie_genre and not is_tv_genre:
                    print(f"⚠️ Unknown genre ID {genre_id}, using as fallback for both")
                    movie_mapped_ids.append(genre_id)
                    tv_mapped_ids.append(genre_id)
            
            # Remove duplicates while preserving order
            movie_mapped_ids = list(dict.fromkeys(movie_mapped_ids))
            tv_mapped_ids = list(dict.fromkeys(tv_mapped_ids))
            
            # Create final comma-separated strings
            movie_genres_str = ','.join(movie_mapped_ids) if movie_mapped_ids else None
            tv_genres_str = ','.join(tv_mapped_ids) if tv_mapped_ids else None
            
            print(f"🔄 Genre mapping RESULT - Movies: {movie_genres_str}, TV: {tv_genres_str}")
            
            return movie_genres_str, tv_genres_str
            
        except Exception as e:
            print(f"❌ Error mapping genres for mixed content: {e}")
            import traceback
            traceback.print_exc()
            # Fallback: use the original genre string for both
            return genre_ids_str, genre_ids_str
    
    def get_tv_episode_details(self, tv_id: int, season_number: int, episode_number: int) -> Dict:
        """Get detailed information about a specific TV episode"""
        url = f"{self.base_url}/tv/{tv_id}/season/{season_number}/episode/{episode_number}"
        params = {'api_key': self.api_key}
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()