from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class UserCustomCategory(SQLModel, table=True):
    """User-defined custom categories with filter parameters"""
    __tablename__ = "user_custom_categories"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str = Field(index=True)  # User-defined category name
    
    # Filter parameters (stored as strings to match form data)
    media_type: Optional[str] = None  # movie, tv, mixed
    content_sources: Optional[str] = None  # comma-separated list: trending,popular,etc
    genres: Optional[str] = None  # comma-separated genre IDs
    rating_source: Optional[str] = Field(default="tmdb")  # Only TMDB ratings supported
    rating_min: Optional[str] = None  # minimum rating value
    year_from: Optional[str] = None  # start year
    year_to: Optional[str] = None  # end year
    studios: Optional[str] = None  # comma-separated studio IDs
    streaming: Optional[str] = None  # comma-separated streaming service IDs
    
    # Display properties
    color: str = Field(default="purple")  # Tailwind color for UI
    display_order: int = Field(default=999)  # Order relative to other categories
    is_active: bool = Field(default=True)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    # Total results count (cached for performance)
    cached_count: Optional[int] = None
    count_updated_at: Optional[datetime] = None
    
    class Config:
        # Ensure each user can only have one custom category with the same name
        table_args = {"sqlite_on_conflict_unique": "REPLACE"}
    
    def to_category_dict(self, limit: int = 20) -> dict:
        """Convert to category dictionary format compatible with default categories"""
        return {
            "id": f"custom_{self.id}",
            "title": f"📌 {self.name}",  # Custom emoji for user categories
            "type": "custom",
            "sort": "user_defined",
            "color": self.color,
            "order": self.display_order,
            "limit": limit,
            "user_id": self.user_id,
            # Store filter parameters for generating content
            "filters": {
                "media_type": self.media_type,
                "content_sources": self.content_sources.split(",") if self.content_sources else [],
                "genres": self.genres.split(",") if self.genres else [],
                "rating_source": self.rating_source,
                "rating_min": self.rating_min,
                "year_from": self.year_from,
                "year_to": self.year_to,
                "studios": self.studios.split(",") if self.studios else [],
                "streaming": self.streaming.split(",") if self.streaming else []
            }
        }
    
    def get_filter_summary(self) -> str:
        """Generate a human-readable summary of the filters"""
        parts = []
        
        if self.media_type and self.media_type != "mixed":
            parts.append(f"📺 {self.media_type.title()}")
        
        if self.rating_min:
            parts.append(f"⭐ {self.rating_min}+ (TMDB)")
        
        if self.year_from or self.year_to:
            if self.year_from and self.year_to:
                parts.append(f"📅 {self.year_from}-{self.year_to}")
            elif self.year_from:
                parts.append(f"📅 {self.year_from}+")
            elif self.year_to:
                parts.append(f"📅 -{self.year_to}")
        
        if self.genres:
            genre_count = len(self.genres.split(","))
            parts.append(f"🎭 {genre_count} genre{'s' if genre_count > 1 else ''}")
        
        if self.studios:
            studio_count = len(self.studios.split(","))
            parts.append(f"🏢 {studio_count} studio{'s' if studio_count > 1 else ''}")
        
        if self.streaming:
            streaming_count = len(self.streaming.split(","))
            parts.append(f"📱 {streaming_count} service{'s' if streaming_count > 1 else ''}")
        
        return " • ".join(parts) if parts else "All content"