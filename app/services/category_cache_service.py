"""
Category Cache Service - Handles cached TMDB data for performance
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlmodel import Session, select

from ..models.category_cache import CategoryCache
from ..services.tmdb_service import TMDBService

logger = logging.getLogger(__name__)


class CategoryCacheService:
    """Service for managing cached category data"""
    
    def __init__(self, session: Session):
        self.session = session
        self.tmdb_service = TMDBService(session)
    
    def get_cached_category(
        self, 
        media_type: str, 
        category: str, 
        page: int = 1,
        fallback_to_api: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached category data, with optional fallback to fresh API call
        
        Args:
            media_type: 'movie' or 'tv'
            category: 'popular', 'top_rated', 'upcoming', 'on_the_air'
            page: Page number (currently only page 1 is cached)
            fallback_to_api: If True, fetch from TMDB API if cache miss/expired
            
        Returns:
            TMDB response data or None if not available
        """
        # Generate cache key
        cache_key = CategoryCache.generate_cache_key(media_type, category, page)
        
        try:
            # Try to get from cache first
            stmt = select(CategoryCache).where(CategoryCache.cache_key == cache_key)
            cache_entry = self.session.exec(stmt).first()
            
            if cache_entry and not cache_entry.is_expired:
                logger.info(f"🚀 Cache hit for {cache_key} (cached {cache_entry.item_count} items)")
                return cache_entry.get_data()
            
            if cache_entry and cache_entry.is_expired:
                logger.warning(f"⚠️ Cache expired for {cache_key} (expired at {cache_entry.expires_at})")
            else:
                logger.warning(f"❌ Cache miss for {cache_key} (no cache entry found)")
            
            # Fallback to API if enabled and no valid cache
            if fallback_to_api:
                logger.warning(f"🔄 Fetching fresh data from TMDB API for {cache_key} (cache unavailable)")
                return self._fetch_from_api(media_type, category, page)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting cached category {cache_key}: {e}")
            if fallback_to_api:
                return self._fetch_from_api(media_type, category, page)
            return None
    
    def _fetch_from_api(self, media_type: str, category: str, page: int) -> Optional[Dict[str, Any]]:
        """Fetch category data directly from TMDB API"""
        try:
            if category == "popular":
                return self.tmdb_service.get_popular(media_type, page=page)
            elif category == "top_rated":
                return self.tmdb_service.get_top_rated(media_type, page=page)
            elif category == "upcoming" and media_type == "movie":
                return self.tmdb_service.get_upcoming_movies(page=page)
            elif category == "on_the_air" and media_type == "tv":
                return self.tmdb_service.discover_tv(page=page, sort_by="popularity.desc")
            else:
                logger.warning(f"Unknown category combination: {media_type}/{category}")
                return None
        except Exception as e:
            logger.error(f"Failed to fetch from TMDB API for {media_type}/{category}: {e}")
            return None
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about cached data"""
        try:
            stmt = select(CategoryCache)
            all_entries = self.session.exec(stmt).all()
            
            total_entries = len(all_entries)
            expired_entries = sum(1 for entry in all_entries if entry.is_expired)
            valid_entries = total_entries - expired_entries
            total_items = sum(entry.item_count for entry in all_entries if not entry.is_expired)
            
            # Group by media type
            by_media_type = {}
            for entry in all_entries:
                if not entry.is_expired:
                    if entry.media_type not in by_media_type:
                        by_media_type[entry.media_type] = {"categories": 0, "items": 0}
                    by_media_type[entry.media_type]["categories"] += 1
                    by_media_type[entry.media_type]["items"] += entry.item_count
            
            return {
                "total_entries": total_entries,
                "valid_entries": valid_entries,
                "expired_entries": expired_entries,
                "total_cached_items": total_items,
                "by_media_type": by_media_type,
                "last_updated": max(
                    (entry.cached_at for entry in all_entries if not entry.is_expired),
                    default=None
                )
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}
    
    def invalidate_cache(self, media_type: Optional[str] = None, category: Optional[str] = None):
        """
        Invalidate cache entries
        
        Args:
            media_type: If specified, only invalidate this media type
            category: If specified, only invalidate this category
        """
        try:
            stmt = select(CategoryCache)
            
            if media_type:
                stmt = stmt.where(CategoryCache.media_type == media_type)
            if category:
                stmt = stmt.where(CategoryCache.category == category)
            
            entries_to_delete = self.session.exec(stmt).all()
            
            for entry in entries_to_delete:
                self.session.delete(entry)
            
            self.session.commit()
            
            logger.info(f"Invalidated {len(entries_to_delete)} cache entries")
            return len(entries_to_delete)
            
        except Exception as e:
            logger.error(f"Error invalidating cache: {e}")
            self.session.rollback()
            return 0