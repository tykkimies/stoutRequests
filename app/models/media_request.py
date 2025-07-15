from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class MediaType(str, Enum):
    MOVIE = "movie"
    TV = "tv"


class RequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"  # Download completed in Radarr/Sonarr, not yet in Plex
    AVAILABLE = "available"
    REJECTED = "rejected"


class MediaRequest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    tmdb_id: int = Field(index=True)
    media_type: MediaType
    title: str
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    release_date: Optional[str] = None
    status: RequestStatus = Field(default=RequestStatus.PENDING)
    radarr_id: Optional[int] = None
    sonarr_id: Optional[int] = None
    season_number: Optional[int] = None  # For TV shows
    is_season_request: bool = Field(default=False)  # True if requesting specific season
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[int] = Field(default=None, foreign_key="user.id")