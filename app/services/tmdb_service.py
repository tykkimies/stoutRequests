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
                       region: str = "US") -> Dict:
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
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        self._process_results(data.get('results', []))
        return data
    
    def discover_tv(self, page: int = 1, sort_by: str = 'popularity.desc',
                   with_genres: str = None, vote_average_gte: float = None,
                   vote_count_gte: int = None,
                   with_networks: str = None, with_companies: str = None, with_watch_providers: str = None,
                   first_air_date_gte: str = None, first_air_date_lte: str = None,
                   region: str = "US") -> Dict:
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
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
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
                            region=region
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
                            region=region
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
            
            # Calculate pages for each media type to get roughly equal representation
            # For page 1, get 10 items from each. For page 2+, alternate or split accordingly
            items_per_type = 10  # 10 movies + 10 TV shows = 20 total per page
            
            # Get movie results
            try:
                movie_results = self.get_category_content(
                    "movie", category, page=page,
                    with_genres=movie_genres, vote_average_gte=vote_average_gte,
                    with_companies=with_companies, with_watch_providers=with_watch_providers,
                    primary_release_date_gte=primary_release_date_gte, 
                    primary_release_date_lte=primary_release_date_lte,
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
                    first_air_date_gte=first_air_date_gte,
                    first_air_date_lte=first_air_date_lte,
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
        Some genres have different IDs between movies and TV shows.
        """
        if not genre_ids_str:
            return None, None
            
        try:
            # Get both genre lists to create mapping
            movie_genres = self.get_genre_list("movie").get('genres', [])
            tv_genres = self.get_genre_list("tv").get('genres', [])
            
            # Create name-to-ID mappings
            movie_genre_map = {genre['name']: str(genre['id']) for genre in movie_genres}
            tv_genre_map = {genre['name']: str(genre['id']) for genre in tv_genres}
            
            # Parse the input genre IDs
            input_genre_ids = genre_ids_str.split(',')
            
            # Map each genre ID to names, then back to appropriate IDs
            movie_mapped_ids = []
            tv_mapped_ids = []
            
            for genre_id in input_genre_ids:
                genre_id = genre_id.strip()
                
                # Find the genre name by checking both movie and TV genre lists
                genre_name = None
                
                # Check movie genres first
                for genre in movie_genres:
                    if str(genre['id']) == genre_id:
                        genre_name = genre['name']
                        break
                        
                # If not found in movies, check TV genres
                if not genre_name:
                    for genre in tv_genres:
                        if str(genre['id']) == genre_id:
                            genre_name = genre['name']
                            break
                
                # If we found the genre name, map it to appropriate IDs
                if genre_name:
                    # Map to movie ID if exists
                    if genre_name in movie_genre_map:
                        movie_mapped_ids.append(movie_genre_map[genre_name])
                    
                    # Map to TV ID if exists
                    if genre_name in tv_genre_map:
                        tv_mapped_ids.append(tv_genre_map[genre_name])
                else:
                    # If we can't find the genre name, use the original ID for both
                    # This handles cases where the genre might not be in our cache
                    movie_mapped_ids.append(genre_id)
                    tv_mapped_ids.append(genre_id)
            
            movie_genres_str = ','.join(movie_mapped_ids) if movie_mapped_ids else None
            tv_genres_str = ','.join(tv_mapped_ids) if tv_mapped_ids else None
            
            return movie_genres_str, tv_genres_str
            
        except Exception as e:
            print(f"Error mapping genres for mixed content: {e}")
            # Fallback: use the original genre string for both
            return genre_ids_str, genre_ids_str
    
    def get_tv_episode_details(self, tv_id: int, season_number: int, episode_number: int) -> Dict:
        """Get detailed information about a specific TV episode"""
        url = f"{self.base_url}/tv/{tv_id}/season/{season_number}/episode/{episode_number}"
        params = {'api_key': self.api_key}
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()