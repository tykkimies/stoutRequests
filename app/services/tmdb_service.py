import requests
import aiohttp
import asyncio
from typing import Dict, Optional, List
from sqlmodel import Session
from datetime import datetime, timedelta

from ..services.settings_service import SettingsService


class TMDBService:
    # Default TMDB API key - shared across all CuePlex installations
    DEFAULT_API_KEY = "27c398b400410d75da7a78e31d8f4c74"
    
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
        """Get detailed TV show information including seasons/episodes"""
        url = f"{self.base_url}/tv/{tv_id}"
        params = {
            'api_key': self.api_key,
            'append_to_response': 'credits,external_ids'
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        # Get detailed season information with episodes
        if 'seasons' in data:
            detailed_seasons = []
            for season in data['seasons']:
                season_number = season.get('season_number', 0)
                
                # Get detailed season info with episodes
                season_url = f"{self.base_url}/tv/{tv_id}/season/{season_number}"
                season_params = {'api_key': self.api_key}
                
                try:
                    season_response = requests.get(season_url, params=season_params)
                    season_response.raise_for_status()
                    detailed_season = season_response.json()
                    detailed_seasons.append(detailed_season)
                except Exception as e:
                    print(f"⚠️ Error fetching season {season_number} details: {e}")
                    # Fallback to basic season info
                    detailed_seasons.append(season)
            
            # Replace seasons with detailed data
            data['seasons'] = detailed_seasons
        
        return data
    
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
        
        Uses cache for page 1 requests without filters for performance optimization.
        """
        # Check if this request can use cache (page 1, no filters, cacheable category)
        has_filters = any([
            with_genres, vote_average_gte, with_companies, with_networks,
            with_watch_providers, primary_release_date_gte, primary_release_date_lte,
            first_air_date_gte, first_air_date_lte
        ])
        
        cacheable_categories = ['popular', 'top_rated', 'upcoming', 'on_the_air', 'trending']
        can_use_cache = (
            page == 1 and 
            not has_filters and 
            category in cacheable_categories and
            media_type in ['movie', 'tv']  # Only cache single media types
        )
        
        if can_use_cache:
            try:
                from ..services.category_cache_service import CategoryCacheService
                cache_service = CategoryCacheService(self.session)
                cached_data = cache_service.get_cached_category(
                    media_type=media_type,
                    category=category,
                    page=page,
                    fallback_to_api=False  # Let this method handle the fallback
                )
                
                if cached_data:
                    # Cache hit - return cached data
                    return cached_data
                    
            except Exception as e:
                # Log cache error but continue with API fallback
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Cache lookup failed for {media_type}/{category}: {e}")
        
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
        print(f"🔍 _GET_MIXED_CONTENT DEBUG:")
        print(f"  - category: '{category}'")
        print(f"  - page: {page}")
        print(f"  - with_genres: '{with_genres}'")
        print(f"  - vote_average_gte: {vote_average_gte}")
        print(f"  - primary_release_date_gte/lte: {primary_release_date_gte}/{primary_release_date_lte}")
        print(f"  - first_air_date_gte/lte: {first_air_date_gte}/{first_air_date_lte}")
        
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
            
            # CRITICAL FIX: Proper pagination for mixed content
            # Each page should fetch the same page from both movie and TV APIs
            # This ensures consistent pagination throughout infinite scroll
            
            # Get movie results using the same page number
            print(f"🎬 CALLING movie get_category_content:")
            print(f"  - media_type: 'movie'")
            print(f"  - category: '{category}'")
            print(f"  - page: {page}")
            print(f"  - with_genres: '{movie_genres}'")
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
                print(f"🔍 MIXED CONTENT: Page {page} - Got {len(movies)} movies")
            except Exception as e:
                print(f"Error fetching movies for mixed content: {e}")
                movies = []
                movie_results = {'total_pages': 1, 'total_results': 0}
            
            # Get TV results using the same page number
            print(f"📺 CALLING TV get_category_content:")
            print(f"  - media_type: 'tv'")
            print(f"  - category: '{category}'")
            print(f"  - page: {page}")
            print(f"  - with_genres: '{tv_genres}'")
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
                print(f"🔍 MIXED CONTENT: Page {page} - Got {len(tv_shows)} TV shows")
            except Exception as e:
                print(f"Error fetching TV shows for mixed content: {e}")
                tv_shows = []
                tv_results = {'total_pages': 1, 'total_results': 0}
            
            # Combine results by interleaving movies and TV shows
            # CRITICAL FIX: Don't artificially limit to 20 items - let TMDB pagination work
            combined_results = []
            max_items = max(len(movies), len(tv_shows))
            for i in range(max_items):
                if i < len(movies):
                    combined_results.append(movies[i])
                if i < len(tv_shows):
                    combined_results.append(tv_shows[i])
            
            # Sort combined results by popularity for better mixing
            def get_popularity(item):
                return item.get('popularity', 0)
            
            combined_results.sort(key=get_popularity, reverse=True)
            
            # CRITICAL FIX: Correct pagination calculation
            # Use the MAXIMUM total pages from both APIs to ensure all content is accessible
            movie_total_pages = movie_results.get('total_pages', 1)
            tv_total_pages = tv_results.get('total_pages', 1)
            # Use the maximum to ensure we can access all content from both APIs
            max_total_pages = max(movie_total_pages, tv_total_pages)
            
            # Calculate total results 
            movie_total_results = movie_results.get('total_results', 0)
            tv_total_results = tv_results.get('total_results', 0)
            total_results = movie_total_results + tv_total_results
            
            print(f"🔍 MIXED CONTENT FINAL RESULTS:")
            print(f"  - Page {page}/{max_total_pages} - Combined {len(combined_results)} items")
            print(f"  - Movie total pages: {movie_total_pages}, TV total pages: {tv_total_pages}")
            print(f"  - Movie total results: {movie_total_results}, TV total results: {tv_total_results}")
            print(f"  - Combined total results: {total_results}")
            print(f"  - Final breakdown:")
            final_movie_count = len([r for r in combined_results if r.get('media_type') == 'movie'])
            final_tv_count = len([r for r in combined_results if r.get('media_type') == 'tv'])
            print(f"    - Movies: {final_movie_count}")
            print(f"    - TV shows: {final_tv_count}")
            
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
    
    # ==========================================
    # ASYNC METHODS for PARALLEL API CALLS
    # ==========================================
    
    async def get_multiple_details_async(self, items: List[Dict], media_type: str = None) -> List[Dict]:
        """
        Fetch details for multiple items in parallel using async requests.
        Significantly faster than sequential requests for recommendations.
        
        Args:
            items: List of items with 'id' and optionally 'media_type'
            media_type: Default media type if not specified in items
            
        Returns:
            List of detailed item data from TMDB
        """
        async with aiohttp.ClientSession() as session:
            tasks = []
            
            for item in items:
                item_media_type = item.get('media_type', media_type)
                item_id = item.get('id')
                
                if item_id and item_media_type:
                    task = self._fetch_item_details_async(session, item_id, item_media_type)
                    tasks.append(task)
            
            # Execute all requests in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter out exceptions and None results
            valid_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"⚠️ Error fetching details for item {items[i].get('id')}: {result}")
                elif result:
                    valid_results.append(result)
            
            return valid_results
    
    async def _fetch_item_details_async(self, session: aiohttp.ClientSession, item_id: int, media_type: str) -> Dict:
        """Fetch individual item details using async HTTP"""
        endpoint = "movie" if media_type == "movie" else "tv"
        url = f"{self.base_url}/{endpoint}/{item_id}"
        params = {'api_key': self.api_key}
        
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    # Process images like sync version
                    if data.get('poster_path'):
                        data['poster_url'] = f"{self.image_base_url}{data['poster_path']}"
                    if data.get('backdrop_path'):
                        data['backdrop_url'] = f"{self.image_base_url}{data['backdrop_path']}"
                    return data
                else:
                    print(f"⚠️ TMDB API error {response.status} for {media_type} {item_id}")
                    return None
        except Exception as e:
            print(f"⚠️ Network error fetching {media_type} {item_id}: {e}")
            return None
    
    async def get_category_content_async(self, media_type: str, category: str, page: int = 1) -> Dict:
        """Truly async version of get_category_content for parallel loading"""
        try:
            # Check cache first for page 1 requests
            if page == 1:
                try:
                    from ..services.category_cache_service import CategoryCacheService
                    cache_service = CategoryCacheService(self.session)
                    cached_data = cache_service.get_cached_category(
                        media_type=media_type,
                        category=category,
                        page=page,
                        fallback_to_api=False
                    )
                    if cached_data:
                        print(f"🚀 Cache hit for {media_type}/{category} page {page}")
                        return cached_data
                except Exception as e:
                    print(f"⚠️ Cache lookup failed: {e}")
            
            # Async API call using aiohttp
            async with aiohttp.ClientSession() as session:
                url, params = self._build_category_url(media_type, category, page)
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"🚀 Async API call successful for {media_type}/{category} page {page}")
                        return data
                    else:
                        print(f"⚠️ TMDB API error {response.status} for {media_type}/{category}")
                        return {'results': [], 'total_pages': 0, 'total_results': 0}
                        
        except Exception as e:
            print(f"⚠️ Error in async category content: {e}")
            return {'results': [], 'total_pages': 0, 'total_results': 0}
    
    def _build_category_url(self, media_type: str, category: str, page: int = 1) -> tuple:
        """Build TMDB API URL and params for a category"""
        params = {
            'api_key': self.api_key,
            'page': page,
            'region': 'US'
        }
        
        # Map category to appropriate endpoint and params
        mapping = self.category_mappings.get(media_type, {}).get(category, {})
        
        if mapping.get('use_discover'):
            # Use discover endpoint
            url = f"{self.base_url}/discover/{media_type}"
            params['sort_by'] = mapping.get('sort_by', 'popularity.desc')
            params.update(mapping.get('additional_params', {}))
        elif category == 'trending':
            # Use trending endpoint
            url = f"{self.base_url}/trending/{media_type}/week"
        else:
            # Use standard endpoints
            url = f"{self.base_url}/{media_type}/{category}"
            
        return url, params
    
    async def get_personalized_recommendations_async(self, user_requests: List, limit: int = 30) -> List[Dict]:
        """
        Generate personalized recommendations based on user requests using parallel API calls.
        This replaces the sequential TMDB API calls with parallel processing.
        
        Args:
            user_requests: List of MediaRequest objects from database  
            limit: Maximum number of recommendations to return
            
        Returns:
            List of recommendation items with media_type and recommendation_reason
        """
        print(f"🚀 Starting parallel recommendations for {len(user_requests)} user requests")
        import time
        start_time = time.time()
        
        if not user_requests:
            # No request history, fall back to popular content
            print("📊 No request history, falling back to popular content")
            try:
                async with aiohttp.ClientSession() as session:
                    # Fetch popular movies and TV in parallel
                    movie_task = self._fetch_category_async(session, 'movie', 'popular', 1)
                    tv_task = self._fetch_category_async(session, 'tv', 'popular', 1)
                    
                    movie_results, tv_results = await asyncio.gather(movie_task, tv_task, return_exceptions=True)
                    
                    all_results = []
                    if not isinstance(movie_results, Exception) and movie_results:
                        for item in movie_results.get('results', [])[:15]:
                            item['media_type'] = 'movie'
                            item['recommendation_reason'] = 'Popular content'
                            all_results.append(item)
                    
                    if not isinstance(tv_results, Exception) and tv_results:
                        for item in tv_results.get('results', [])[:15]:
                            item['media_type'] = 'tv'
                            item['recommendation_reason'] = 'Popular content'
                            all_results.append(item)
                    
                    return all_results[:limit]
            except Exception as e:
                print(f"⚠️ Error in fallback recommendations: {e}")
                return []
        
        # Prepare items for parallel fetching
        items_to_fetch = []
        request_info = {}
        
        print(f"🔍 Processing up to 10 user requests for recommendations...")
        for i, user_request in enumerate(user_requests[:10]):  # Limit to 10 to avoid overwhelming
            try:
                request_media_type = user_request.media_type.value if hasattr(user_request.media_type, 'value') else str(user_request.media_type)
                print(f"  {i+1}. Processing: {user_request.title} (TMDB: {user_request.tmdb_id}, Type: {request_media_type})")
                
                # Add the original requested item to get its recommendations
                item_key = f"{user_request.tmdb_id}_{request_media_type}"
                items_to_fetch.append({
                    'id': user_request.tmdb_id,
                    'media_type': request_media_type
                })
                request_info[item_key] = {
                    'title': user_request.title,
                    'media_type': request_media_type
                }
                
            except Exception as request_error:
                print(f"⚠️ Error processing request {user_request.title}: {request_error}")
                continue
        
        # Fetch all items in parallel
        print(f"🔍 Fetching details for {len(items_to_fetch)} items...")
        try:
            detailed_items = await self.get_multiple_details_async(items_to_fetch)
            print(f"🔍 Got details for {len(detailed_items) if detailed_items else 0} items")
            
            if not detailed_items:
                print("⚠️ No detailed items received from TMDB, cannot generate recommendations")
                return []
            
            # Now get similar/recommended items for each in parallel
            recommendation_tasks = []
            async with aiohttp.ClientSession() as session:
                for i, item in enumerate(detailed_items):
                    if item and item.get('id'):
                        media_type = item.get('media_type', 'movie')
                        title = item.get('title') or item.get('name', 'Unknown')
                        print(f"  {i+1}. Creating recommendation tasks for: {title} (ID: {item['id']}, Type: {media_type})")
                        
                        # Get similar items
                        similar_task = self._fetch_similar_async(session, item['id'], media_type)
                        recommendation_tasks.append((similar_task, item, 'similar'))
                        
                        # Get recommended items
                        rec_task = self._fetch_recommendations_async(session, item['id'], media_type)
                        recommendation_tasks.append((rec_task, item, 'recommended'))
                    else:
                        print(f"  {i+1}. Skipping invalid item: {item}")
                
                print(f"🔍 Created {len(recommendation_tasks)} recommendation tasks")
                
                # Execute all recommendation fetches in parallel
                if recommendation_tasks:
                    task_list = [task[0] for task in recommendation_tasks]
                    task_metadata = [(task[1], task[2]) for task in recommendation_tasks]
                    
                    print(f"🔍 Executing {len(task_list)} recommendation API calls...")
                    results = await asyncio.gather(*task_list, return_exceptions=True)
                    print(f"🔍 Got {len(results)} results from recommendation API calls")
                    
                    # Process results
                    recommendation_items = []
                    seen_ids = set()
                    successful_results = 0
                    failed_results = 0
                    
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            failed_results += 1
                            print(f"⚠️ Exception in result {i+1}: {result}")
                            continue
                            
                        original_item, rec_type = task_metadata[i]
                        original_title = original_item.get('title') or original_item.get('name', 'Unknown')
                        
                        if result and 'results' in result:
                            successful_results += 1
                            items_found = len(result['results'])
                            print(f"  Result {i+1}: {items_found} {rec_type} items for {original_title}")
                            
                            for rec_item in result['results'][:5]:  # Top 5 from each
                                item_id = f"{rec_item['id']}_{original_item['media_type']}"
                                if item_id not in seen_ids and len(recommendation_items) < limit:
                                    rec_item['media_type'] = original_item['media_type']
                                    rec_item['recommendation_reason'] = f"{'Similar to' if rec_type == 'similar' else 'Recommended for'} {original_title}"
                                    recommendation_items.append(rec_item)
                                    seen_ids.add(item_id)
                        else:
                            failed_results += 1
                            print(f"  Result {i+1}: Empty or invalid result for {original_title} ({rec_type})")
                    
                    fetch_time = time.time() - start_time
                    print(f"📊 Recommendation results summary:")
                    print(f"  - Successful API calls: {successful_results}")
                    print(f"  - Failed API calls: {failed_results}")
                    print(f"  - Total recommendations found: {len(recommendation_items)}")
                    print(f"  - Time taken: {fetch_time:.2f}s")
                    print(f"✅ Parallel recommendations completed - returning {len(recommendation_items)} items")
                    return recommendation_items[:limit]
                    
        except Exception as parallel_error:
            print(f"⚠️ Parallel recommendations failed: {parallel_error}")
            return []
        
        return []
    
    async def _fetch_category_async(self, session: aiohttp.ClientSession, media_type: str, category: str, page: int) -> Dict:
        """Fetch category content using async HTTP"""
        endpoint = "movie" if media_type == "movie" else "tv"
        url = f"{self.base_url}/{endpoint}/{category}"
        params = {'api_key': self.api_key, 'page': page}
        
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"⚠️ TMDB API error {response.status} for {media_type} {category}")
                    return {'results': []}
        except Exception as e:
            print(f"⚠️ Network error fetching {media_type} {category}: {e}")
            return {'results': []}
    
    async def _fetch_similar_async(self, session: aiohttp.ClientSession, item_id: int, media_type: str) -> Dict:
        """Fetch similar items using async HTTP"""
        endpoint = "movie" if media_type == "movie" else "tv"
        url = f"{self.base_url}/{endpoint}/{item_id}/similar"
        params = {'api_key': self.api_key}
        
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {'results': []}
        except Exception as e:
            print(f"⚠️ Error fetching similar for {media_type} {item_id}: {e}")
            return {'results': []}
    
    async def _fetch_recommendations_async(self, session: aiohttp.ClientSession, item_id: int, media_type: str) -> Dict:
        """Fetch recommendations using async HTTP"""
        endpoint = "movie" if media_type == "movie" else "tv"  
        url = f"{self.base_url}/{endpoint}/{item_id}/recommendations"
        params = {'api_key': self.api_key}
        
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {'results': []}
        except Exception as e:
            print(f"⚠️ Error fetching recommendations for {media_type} {item_id}: {e}")
            return {'results': []}