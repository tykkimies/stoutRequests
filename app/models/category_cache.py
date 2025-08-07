from datetime import datetime
from typing import Optional, Any, Dict
import json
from sqlmodel import SQLModel, Field, Column, DateTime, Text


class CategoryCache(SQLModel, table=True):
    """
    Cache storage for TMDB category data to improve homepage performance
    """
    __tablename__ = "category_cache"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    cache_key: str = Field(index=True, unique=True, description="Unique key for the cached data (e.g., 'movie_popular', 'tv_top_rated')")
    media_type: str = Field(index=True, description="Type of media: 'movie' or 'tv'")
    category: str = Field(index=True, description="Category name: 'popular', 'top_rated', 'upcoming', 'on_the_air'")
    data: str = Field(sa_column=Column(Text), description="JSON-serialized TMDB response data")
    cached_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime))
    expires_at: datetime = Field(sa_column=Column(DateTime), description="Cache expiration timestamp")
    page_count: int = Field(default=1, description="Number of pages cached")
    item_count: int = Field(default=0, description="Total number of items in cache")
    
    def get_data(self) -> Dict[str, Any]:
        """Parse and return the cached JSON data"""
        try:
            return json.loads(self.data)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_data(self, data: Dict[str, Any]):
        """Serialize and store the data as JSON"""
        self.data = json.dumps(data)
        if isinstance(data, dict) and "results" in data:
            self.item_count = len(data["results"])
    
    @property
    def is_expired(self) -> bool:
        """Check if the cache entry has expired"""
        return datetime.utcnow() > self.expires_at
    
    @classmethod
    def generate_cache_key(cls, media_type: str, category: str, page: int = 1) -> str:
        """Generate a consistent cache key"""
        return f"{media_type}_{category}_page_{page}"