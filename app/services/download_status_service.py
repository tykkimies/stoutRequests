"""
Download Status Service - Tracks real download status from Radarr/Sonarr

This service handles the proper status lifecycle:
1. approved → processing (when successfully sent to Radarr/Sonarr)
2. processing → downloading (when download starts)
3. downloading → downloaded (when download completes)
4. downloaded → available (when found in Plex)
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlmodel import Session, select
from ..models.media_request import MediaRequest, RequestStatus, MediaType
from ..services.radarr_service import RadarrService
from ..services.sonarr_service import SonarrService


class DownloadStatusService:
    def __init__(self, session: Session):
        self.session = session
    
    async def check_download_statuses(self) -> Dict[str, int]:
        """
        Check download status for all requests and update accordingly.
        Returns statistics about updates made.
        """
        print("🚀 DOWNLOAD STATUS SERVICE: Starting check...")
        stats = {
            'checked': 0,
            'updated_to_downloading': 0,
            'updated_to_downloaded': 0,
            'errors': 0
        }
        
        try:
            # Get requests that need status checking
            requests_to_check = self._get_requests_needing_status_check()
            stats['checked'] = len(requests_to_check)
            
            print(f"🔄 DOWNLOAD STATUS: Found {len(requests_to_check)} requests to check...")
            for req in requests_to_check:
                print(f"   - Request {req.id}: {req.title} (Status: {req.status.value}, Radarr ID: {req.radarr_id}, Sonarr ID: {req.sonarr_id})")
            
            for request in requests_to_check:
                try:
                    updated = await self._update_request_download_status(request)
                    if updated:
                        if request.status == RequestStatus.DOWNLOADING:
                            stats['updated_to_downloading'] += 1
                        elif request.status == RequestStatus.DOWNLOADED:
                            stats['updated_to_downloaded'] += 1
                except Exception as e:
                    print(f"❌ Error checking status for request {request.id}: {e}")
                    stats['errors'] += 1
            
            self.session.commit()
            print(f"✅ Download status check complete: {stats}")
            
        except Exception as e:
            print(f"❌ Error in download status check: {e}")
            self.session.rollback()
            stats['errors'] += 1
        
        return stats
    
    def _get_requests_needing_status_check(self) -> List[MediaRequest]:
        """Get requests that need their download status checked"""
        statement = select(MediaRequest).where(
            MediaRequest.status.in_([
                RequestStatus.APPROVED,     # Just approved, check if in Radarr/Sonarr
                RequestStatus.DOWNLOADING,  # Currently downloading, check progress
            ]),
            # Only check requests that have been sent to services
            MediaRequest.radarr_id.isnot(None) | MediaRequest.sonarr_id.isnot(None)
        )
        return list(self.session.exec(statement).all())
    
    async def _update_request_download_status(self, request: MediaRequest) -> bool:
        """
        Update a single request's download status.
        Returns True if status was updated.
        """
        try:
            if request.media_type == MediaType.MOVIE:
                return await self._check_radarr_status(request)
            elif request.media_type == MediaType.TV:
                return await self._check_sonarr_status(request)
        except Exception as e:
            print(f"Error checking status for {request.media_type} request {request.id}: {e}")
            return False
        
        return False
    
    async def _check_radarr_status(self, request: MediaRequest) -> bool:
        """Check Radarr for movie download status"""
        if not request.radarr_id:
            return False
        
        try:
            radarr_service = RadarrService(self.session)
            
            # Get movie details from Radarr
            movie_details = radarr_service.get_movie_details(request.radarr_id)
            if not movie_details:
                return False
            
            # Check movie status in Radarr
            old_status = request.status
            new_status = self._determine_status_from_radarr(movie_details, request.status)
            
            if new_status != old_status:
                request.status = new_status
                request.updated_at = datetime.utcnow()
                self.session.add(request)
                print(f"📦 Movie '{request.title}' status: {old_status.value} → {new_status.value}")
                return True
                
        except Exception as e:
            print(f"Error checking Radarr status for request {request.id}: {e}")
        
        return False
    
    async def _check_sonarr_status(self, request: MediaRequest) -> bool:
        """Check Sonarr for TV show download status"""
        if not request.sonarr_id:
            return False
        
        try:
            sonarr_service = SonarrService(self.session)
            
            # Get series details from Sonarr
            series_details = sonarr_service.get_series_details(request.sonarr_id)
            if not series_details:
                return False
            
            # Check series status in Sonarr
            old_status = request.status
            new_status = self._determine_status_from_sonarr(series_details, request.status)
            
            if new_status != old_status:
                request.status = new_status
                request.updated_at = datetime.utcnow()
                self.session.add(request)
                print(f"📺 TV Show '{request.title}' status: {old_status.value} → {new_status.value}")
                return True
                
        except Exception as e:
            print(f"Error checking Sonarr status for request {request.id}: {e}")
        
        return False
    
    def _determine_status_from_radarr(self, movie_details: Dict, current_status: RequestStatus) -> RequestStatus:
        """Determine request status based on Radarr movie details"""
        # Check if movie has been downloaded
        if movie_details.get('hasFile', False):
            return RequestStatus.DOWNLOADED
        
        # Check if movie is currently downloading
        if movie_details.get('isAvailable', False) or movie_details.get('downloaded', False):
            return RequestStatus.DOWNLOADED
        
        # Check if movie is being monitored and searched
        if movie_details.get('monitored', False):
            return RequestStatus.DOWNLOADING
        
        # If in Radarr but not monitored, consider it processing
        return RequestStatus.APPROVED  # Keep as approved until we see download activity
    
    def _determine_status_from_sonarr(self, series_details: Dict, current_status: RequestStatus) -> RequestStatus:
        """Determine request status based on Sonarr series details"""
        # Check overall series statistics
        statistics = series_details.get('statistics', {})
        
        # If we have any downloaded episodes, consider it downloaded
        if statistics.get('episodeFileCount', 0) > 0:
            return RequestStatus.DOWNLOADED
        
        # If series is monitored and has episodes, it's downloading
        if series_details.get('monitored', False) and statistics.get('episodeCount', 0) > 0:
            return RequestStatus.DOWNLOADING
        
        # If in Sonarr but not actively downloading, keep as approved
        return RequestStatus.APPROVED