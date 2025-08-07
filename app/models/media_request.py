from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class MediaType(str, Enum):
    MOVIE = "movie"
    TV = "tv"


class RequestStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    AVAILABLE = "AVAILABLE"
    REJECTED = "REJECTED"


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
    season_number: Optional[int] = None  # For TV shows
    episode_number: Optional[int] = None  # For specific episode requests
    is_season_request: bool = Field(default=False)  # True if requesting specific season
    is_episode_request: bool = Field(default=False)  # True if requesting specific episode
    
    # Multi-instance support
    service_instance_id: Optional[int] = Field(default=None, foreign_key="serviceinstance.id")  # Which instance handled/will handle this request
    requested_quality_tier: Optional[str] = Field(default="standard", max_length=20)  # Quality tier requested ("standard", "4k", "hdr")
    override_quality_profile_id: Optional[int] = Field(default=None)  # Admin override for specific quality profile ID
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[int] = Field(default=None, foreign_key="user.id")