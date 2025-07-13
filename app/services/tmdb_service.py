import requests
from typing import Dict
from sqlmodel import Session

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
        """Get trending movies or TV shows"""
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
        else:
            raise ValueError(f"Invalid media_type: {media_type}")
    
    def get_watch_providers(self, item_id: int, media_type: str) -> Dict:
        """Get watch providers (streaming services) for a movie or TV show"""
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
                       with_companies: str = None, with_watch_providers: str = None,
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
        if with_companies:
            params['with_companies'] = with_companies
        if with_watch_providers:
            params['with_watch_providers'] = with_watch_providers
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        self._process_results(data.get('results', []))
        return data
    
    def discover_tv(self, page: int = 1, sort_by: str = 'popularity.desc',
                   with_genres: str = None, vote_average_gte: float = None,
                   with_networks: str = None, with_watch_providers: str = None,
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
        if with_networks:
            params['with_networks'] = with_networks
        if with_watch_providers:
            params['with_watch_providers'] = with_watch_providers
        
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
    
    def get_tv_episode_details(self, tv_id: int, season_number: int, episode_number: int) -> Dict:
        """Get detailed information about a specific TV episode"""
        url = f"{self.base_url}/tv/{tv_id}/season/{season_number}/episode/{episode_number}"
        params = {'api_key': self.api_key}
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()