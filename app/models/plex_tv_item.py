from sqlmodel import SQLModel, Field, Index
from typing import Optional
from datetime import datetime


class PlexTVItem(SQLModel, table=True):
    __tablename__ = "plex_tv_item"
    __table_args__ = (
        Index("ix_show_season", "show_tmdb_id", "season_number"),
        Index("ix_show_episode", "show_tmdb_id", "season_number", "episode_number"),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    show_tmdb_id: int = Field(index=True)  # TMDB ID of the parent show
    show_title: str
    season_number: int = Field(index=True)
    episode_number: Optional[int] = Field(index=True, default=None)  # None for season-level entries
    episode_title: Optional[str] = None
    plex_key: str  # Plex rating key for this season/episode
    library_section_id: int
    added_at: Optional[datetime] = None  # When item was actually added to Plex
    created_at: datetime = Field(default_factory=datetime.utcnow)  # When synced to our DB
    updated_at: Optional[datetime] = None
    
    @classmethod
    def get_show_completion_status(cls, session, show_tmdb_id: int) -> dict:
        """
        Get completion status for a TV show.
        Returns dict with total_seasons, available_seasons, total_episodes, available_episodes
        """
        from sqlmodel import select, func
        
        # Get all seasons for this show
        seasons_query = select(cls.season_number).where(
            cls.show_tmdb_id == show_tmdb_id,
            cls.episode_number.is_(None)  # Season-level entries only
        ).distinct()
        
        available_seasons = list(session.exec(seasons_query))
        
        # Get all episodes for this show
        episodes_query = select(func.count()).where(
            cls.show_tmdb_id == show_tmdb_id,
            cls.episode_number.isnot(None)  # Episode-level entries only
        )
        
        available_episodes = session.exec(episodes_query).one()
        
        return {
            'available_seasons': len(available_seasons),
            'available_episodes': available_episodes,
            'season_numbers': sorted(available_seasons) if available_seasons else []
        }