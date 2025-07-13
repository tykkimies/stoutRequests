from sqlmodel import SQLModel, Field, Index
from typing import Optional
from datetime import datetime


class PlexLibraryItem(SQLModel, table=True):
    __tablename__ = "plex_library_item"
    __table_args__ = (
        Index("ix_tmdb_media_type", "tmdb_id", "media_type", unique=True),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    plex_key: str = Field(unique=True, index=True)
    tmdb_id: Optional[int] = Field(index=True)
    title: str
    media_type: str  # movie, show (only movies and shows, not episodes/seasons)
    year: Optional[int] = None
    rating_key: str
    library_section_id: int
    added_at: Optional[datetime] = None  # When item was actually added to Plex
    created_at: datetime = Field(default_factory=datetime.utcnow)  # When synced to our DB
    updated_at: Optional[datetime] = None