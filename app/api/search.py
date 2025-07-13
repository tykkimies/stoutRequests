from fastapi import APIRouter, Depends, Query
from sqlmodel import Session
from typing import Optional

from ..core.database import get_session
from ..services.tmdb_service import TMDBService
from ..services.plex_service import PlexService
from ..api.auth import get_current_user
from ..models.user import User

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/")
async def search_media(
    q: str = Query(..., description="Search query"),
    page: int = Query(1, description="Page number"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Search for movies and TV shows"""
    tmdb_service = TMDBService(session)
    plex_service = PlexService(session)
    
    results = tmdb_service.search_multi(q, page)
    
    # Check which items are already in Plex library
    for item in results.get('results', []):
        if item.get('media_type') in ['movie', 'tv']:
            item['in_plex'] = plex_service.check_media_in_library(
                item['id'], 
                item['media_type']
            )
        else:
            item['in_plex'] = False
    
    return results