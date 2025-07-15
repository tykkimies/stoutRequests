"""
Download Status Service - Simple status tracking from Radarr/Sonarr

This service handles the status lifecycle:
1. approved → downloading (when actively downloading in Radarr/Sonarr)  
2. downloading → available (handled by Plex library sync)
"""

from datetime import datetime
from typing import Dict, List
from sqlmodel import Session, select
from ..models.media_request import MediaRequest, RequestStatus, MediaType
from ..services.radarr_service import RadarrService
from ..services.sonarr_service import SonarrService


class DownloadStatusService:
    def __init__(self, session: Session):
        self.session = session
    
    async def check_download_statuses(self) -> Dict[str, int]:
        """
        Check download status for approved requests and update to downloading if active.
        Returns statistics about updates made.
        """
        print("🚀 DOWNLOAD STATUS SERVICE: Starting check...")
        stats = {
            'checked': 0,
            'updated_to_downloading': 0,
            'errors': 0
        }
        
        try:
            # Get approved and downloading requests that have been sent to Radarr/Sonarr
            requests_to_check = self._get_approved_requests()
            stats['checked'] = len(requests_to_check)
            
            print(f"🔄 DOWNLOAD STATUS: Found {len(requests_to_check)} requests to check...")
            for req in requests_to_check:
                print(f"   - Request {req.id}: {req.title} (Status: {req.status.value}, Radarr ID: {req.radarr_id}, Sonarr ID: {req.sonarr_id})")
            
            for request in requests_to_check:
                try:
                    is_downloading = await self._is_actively_downloading(request)
                    
                    if request.status == RequestStatus.APPROVED and is_downloading:
                        # Update approved → downloading
                        request.status = RequestStatus.DOWNLOADING
                        request.updated_at = datetime.utcnow()
                        self.session.add(request)
                        print(f"📦 Updated '{request.title}' status: approved → downloading")
                        stats['updated_to_downloading'] += 1
                    elif request.status == RequestStatus.DOWNLOADING and not is_downloading:
                        # Update downloading → approved (download stopped/failed)
                        request.status = RequestStatus.APPROVED
                        request.updated_at = datetime.utcnow()
                        self.session.add(request)
                        print(f"📦 Updated '{request.title}' status: downloading → approved (no longer downloading)")
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
    
    def _get_approved_requests(self) -> List[MediaRequest]:
        """Get approved and downloading requests that have been sent to Radarr/Sonarr"""
        statement = select(MediaRequest).where(
            MediaRequest.status.in_([RequestStatus.APPROVED, RequestStatus.DOWNLOADING]),
            # Only check requests that have been sent to services
            MediaRequest.radarr_id.isnot(None) | MediaRequest.sonarr_id.isnot(None)
        )
        return list(self.session.exec(statement).all())
    
    async def _is_actively_downloading(self, request: MediaRequest) -> bool:
        """Check if a request is actively downloading in Radarr/Sonarr"""
        try:
            if request.media_type == MediaType.MOVIE and request.radarr_id:
                return await self._is_movie_downloading(request)
            elif request.media_type == MediaType.TV and request.sonarr_id:
                return await self._is_tv_downloading(request)
        except Exception as e:
            print(f"Error checking download status for request {request.id}: {e}")
        
        return False
    
    async def _is_movie_downloading(self, request: MediaRequest) -> bool:
        """Check if movie is actively downloading in Radarr"""
        try:
            radarr_service = RadarrService(self.session)
            
            # First check if movie has already been downloaded
            movie_details = radarr_service.get_movie_details(request.radarr_id)
            if not movie_details:
                return False
            
            # If movie already has file, it's not downloading
            if movie_details.get('hasFile', False):
                return False
            
            # Check Radarr queue for active downloads of this movie
            return self._check_radarr_queue(radarr_service, request.radarr_id)
                
        except Exception as e:
            print(f"Error checking Radarr status for request {request.id}: {e}")
            return False
    
    def _check_radarr_queue(self, radarr_service: RadarrService, radarr_id: int) -> bool:
        """Check if movie is actively downloading in Radarr queue"""
        try:
            import requests
            
            if not radarr_service.base_url or not radarr_service.api_key:
                return False
            
            # Check Radarr queue for active downloads
            response = requests.get(
                f"{radarr_service.base_url}/api/v3/queue",
                headers={"X-Api-Key": radarr_service.api_key}
            )
            response.raise_for_status()
            queue_data = response.json()
            
            # Look for this movie in the download queue
            for item in queue_data.get('records', []):
                if item.get('movieId') == radarr_id:
                    # Movie is in queue, check if it's actively downloading
                    status = item.get('status', '').lower()
                    return status in ['downloading', 'queued', 'grabbing']
            
            return False
            
        except Exception as e:
            print(f"Error checking Radarr queue: {e}")
            return False
    
    async def _is_tv_downloading(self, request: MediaRequest) -> bool:
        """Check if TV show is actively downloading in Sonarr"""
        try:
            sonarr_service = SonarrService(self.session)
            series_details = sonarr_service.get_series_details(request.sonarr_id)
            
            if not series_details:
                return False
            
            # Check if series has episodes to download
            statistics = series_details.get('statistics', {})
            total_episodes = statistics.get('episodeCount', 0)
            downloaded_episodes = statistics.get('episodeFileCount', 0)
            
            # If all episodes are downloaded, it's not downloading
            if downloaded_episodes >= total_episodes:
                return False
            
            # Check Sonarr queue for active downloads of this series
            return self._check_sonarr_queue(sonarr_service, request.sonarr_id)
                
        except Exception as e:
            print(f"Error checking Sonarr status for request {request.id}: {e}")
            return False
    
    def _check_sonarr_queue(self, sonarr_service: SonarrService, sonarr_id: int) -> bool:
        """Check if TV show is actively downloading in Sonarr queue"""
        try:
            import requests
            
            if not sonarr_service.base_url or not sonarr_service.api_key:
                return False
            
            # Check Sonarr queue for active downloads
            response = requests.get(
                f"{sonarr_service.base_url}/api/v3/queue",
                headers={"X-Api-Key": sonarr_service.api_key}
            )
            response.raise_for_status()
            queue_data = response.json()
            
            # Look for this series in the download queue
            for item in queue_data.get('records', []):
                if item.get('seriesId') == sonarr_id:
                    # Series is in queue, check if it's actively downloading
                    status = item.get('status', '').lower()
                    return status in ['downloading', 'queued', 'grabbing']
            
            return False
            
        except Exception as e:
            print(f"Error checking Sonarr queue: {e}")
            return False