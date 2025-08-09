"""
Request Status Service

Handles efficient batch loading and caching of request statuses to prevent N+1 queries.
Used by category loading to check request status for multiple media items at once.
"""

from typing import Dict, List, Optional, Tuple
from sqlmodel import Session, select
from app.models.media_request import MediaRequest, RequestStatus, MediaType
from datetime import datetime, timedelta

class RequestStatusService:
    """Service for batch loading and caching request status lookups"""
    
    def __init__(self, session: Session):
        self.session = session
        self._status_cache = {}
        self._cache_timestamp = None
        self._cache_ttl = 300  # 5 minute cache TTL
    
    async def batch_get_request_status(
        self,
        user_id: int,
        media_items: List[Dict],
        media_type: str = None
    ) -> Dict[Tuple[int, str], Dict]:
        """
        🚀 PERFORMANCE: Batch load request status for multiple media items
        
        Args:
            user_id: User ID to check requests for
            media_items: List of media items with 'id' and 'media_type' keys
            media_type: Optional media type filter (if all items are same type)
            
        Returns:
            Dict mapping (tmdb_id, media_type) -> request status info
        """
        # Extract unique (tmdb_id, media_type) pairs
        if media_type:
            # All items are same type
            item_keys = [(item['id'], media_type) for item in media_items]
        else:
            # Mixed types - get from each item
            item_keys = [(item['id'], item.get('media_type', 'movie')) for item in media_items]
        
        print(f"🚀 Batch loading request status for {len(item_keys)} items for user {user_id}")
        
        # Check cache first
        cache_key = f"user_{user_id}"
        if self._is_cache_valid() and cache_key in self._status_cache:
            cached_data = self._status_cache[cache_key]
            # Filter for requested items
            result = {}
            for key in item_keys:
                if key in cached_data:
                    result[key] = cached_data[key]
                else:
                    result[key] = self._default_status()
            print(f"🚀 Using cached status data for {len([k for k in item_keys if k in cached_data])} items")
            return result
        
        # Load from database
        tmdb_ids = [key[0] for key in item_keys]
        media_types = list(set([key[1] for key in item_keys]))
        
        # Convert string media types to enums for query
        media_type_enums = []
        for mt in media_types:
            if mt == 'movie':
                media_type_enums.append(MediaType.MOVIE)
            elif mt in ['tv', 'show']:
                media_type_enums.append(MediaType.TV)
        
        # Batch query for all request statuses
        query = select(MediaRequest).where(
            MediaRequest.user_id == user_id,
            MediaRequest.tmdb_id.in_(tmdb_ids),
            MediaRequest.media_type.in_(media_type_enums)
        ).order_by(MediaRequest.created_at.desc())
        
        requests = self.session.exec(query).all()
        print(f"🚀 Loaded {len(requests)} request records from database")
        
        # Build status map
        status_map = {}
        for request in requests:
            key = (request.tmdb_id, request.media_type.value)
            if key not in status_map:  # Use most recent request (already ordered)
                status_map[key] = {
                    'status': request.status.value,
                    'request_id': request.id,
                    'created_at': request.created_at,
                    'user_id': request.user_id,
                    'is_season_request': request.is_season_request,
                    'is_episode_request': request.is_episode_request,
                    'season_number': request.season_number,
                    'episode_number': request.episode_number
                }
        
        # Fill in defaults for items without requests
        result = {}
        for key in item_keys:
            if key in status_map:
                result[key] = status_map[key]
            else:
                result[key] = self._default_status()
        
        # Cache the result for this user
        if cache_key not in self._status_cache:
            self._status_cache[cache_key] = {}
        self._status_cache[cache_key].update(result)
        self._cache_timestamp = datetime.utcnow()
        
        print(f"🚀 Cached status data for user {user_id}: {len(result)} items")
        return result
    
    async def batch_get_any_user_requests(
        self,
        media_items: List[Dict],
        media_type: str = None
    ) -> Dict[Tuple[int, str], bool]:
        """
        🚀 PERFORMANCE: Check if ANY user has requested these items
        Used for showing "requested" status regardless of which user requested it
        
        Returns:
            Dict mapping (tmdb_id, media_type) -> has_any_request (bool)
        """
        # Extract unique (tmdb_id, media_type) pairs
        if media_type:
            item_keys = [(item['id'], media_type) for item in media_items]
        else:
            item_keys = [(item['id'], item.get('media_type', 'movie')) for item in media_items]
        
        cache_key = "any_user_requests"
        if self._is_cache_valid() and cache_key in self._status_cache:
            cached_data = self._status_cache[cache_key]
            result = {}
            for key in item_keys:
                result[key] = cached_data.get(key, False)
            return result
        
        # Load from database
        tmdb_ids = [key[0] for key in item_keys]
        media_types = list(set([key[1] for key in item_keys]))
        
        media_type_enums = []
        for mt in media_types:
            if mt == 'movie':
                media_type_enums.append(MediaType.MOVIE)
            elif mt in ['tv', 'show']:
                media_type_enums.append(MediaType.TV)
        
        # Query for any requests (regardless of user)
        query = select(MediaRequest.tmdb_id, MediaRequest.media_type).where(
            MediaRequest.tmdb_id.in_(tmdb_ids),
            MediaRequest.media_type.in_(media_type_enums),
            MediaRequest.status.in_([RequestStatus.PENDING, RequestStatus.APPROVED])
        ).distinct()
        
        requested_items = self.session.exec(query).all()
        
        # Build lookup set
        requested_set = {(item.tmdb_id, item.media_type.value) for item in requested_items}
        
        # Build result
        result = {}
        for key in item_keys:
            result[key] = key in requested_set
        
        # Cache the result
        self._status_cache[cache_key] = result.copy()
        self._cache_timestamp = datetime.utcnow()
        
        return result
    
    def _default_status(self) -> Dict:
        """Default status for items without requests"""
        return {
            'status': 'available',
            'request_id': None,
            'created_at': None,
            'user_id': None,
            'is_season_request': False,
            'is_episode_request': False,
            'season_number': None,
            'episode_number': None
        }
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid based on TTL"""
        if not self._cache_timestamp:
            return False
        return (datetime.utcnow() - self._cache_timestamp).seconds < self._cache_ttl
    
    def invalidate_cache(self, user_id: int = None):
        """Invalidate cache for a specific user or all users"""
        if user_id:
            cache_key = f"user_{user_id}"
            if cache_key in self._status_cache:
                del self._status_cache[cache_key]
        else:
            self._status_cache.clear()
        self._cache_timestamp = None
        print(f"🚀 Invalidated request status cache for {'user ' + str(user_id) if user_id else 'all users'}")


# Singleton instance for request-scoped caching
_request_status_service = None

def get_request_status_service(session: Session) -> RequestStatusService:
    """Get or create request status service instance"""
    global _request_status_service
    if not _request_status_service:
        _request_status_service = RequestStatusService(session)
    return _request_status_service

# Convenience functions
async def batch_get_user_request_status(
    user_id: int,
    media_items: List[Dict],
    media_type: str = None,
    session: Session = None
) -> Dict[Tuple[int, str], Dict]:
    """Convenience function for batch request status lookup"""
    if not session:
        raise ValueError("Session is required for request status lookup")
    
    service = get_request_status_service(session)
    return await service.batch_get_request_status(user_id, media_items, media_type)

async def batch_check_any_requests(
    media_items: List[Dict],
    media_type: str = None,
    session: Session = None
) -> Dict[Tuple[int, str], bool]:
    """Convenience function to check if any user has requested items"""
    if not session:
        raise ValueError("Session is required for request status lookup")
    
    service = get_request_status_service(session)
    return await service.batch_get_any_user_requests(media_items, media_type)