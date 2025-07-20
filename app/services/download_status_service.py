import asyncio
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlmodel import Session, select

from ..models.media_request import MediaRequest, RequestStatus
from ..models.service_instance import ServiceInstance, ServiceType
from ..core.database import get_session


class DownloadStatusService:
    """
    Service to check Radarr/Sonarr download status and update request statuses.
    This service monitors download queues and updates requests accordingly.
    """
    
    def __init__(self, session: Session = None):
        if session is None:
            from ..core.database import engine
            self.session = Session(engine)
            self._owns_session = True
        else:
            self.session = session
            self._owns_session = False
    
    def __del__(self):
        if hasattr(self, '_owns_session') and self._owns_session and hasattr(self, 'session'):
            self.session.close()
    
    async def check_download_status(self) -> Dict[str, Any]:
        """
        Check download status for all approved requests.
        Returns statistics about the check operation.
        """
        stats = {
            'checked': 0,
            'updated_to_downloading': 0,
            'updated_to_downloaded': 0,
            'errors': 0
        }
        
        try:
            # Get all approved requests that might be downloading
            approved_requests = list(self.session.exec(
                select(MediaRequest).where(
                    MediaRequest.status.in_([RequestStatus.APPROVED])
                )
            ))
            
            print(f"🔍 Checking download status for {len(approved_requests)} approved requests")
            
            # Check Radarr instances for movie requests
            movie_requests = [req for req in approved_requests if req.media_type == 'movie']
            if movie_requests:
                movie_stats = await self._check_radarr_downloads(movie_requests)
                stats['checked'] += movie_stats['checked']
                stats['updated_to_downloading'] += movie_stats['updated_to_downloading']
                stats['updated_to_downloaded'] += movie_stats['updated_to_downloaded']
                stats['errors'] += movie_stats['errors']
            
            # Check Sonarr instances for TV show requests
            tv_requests = [req for req in approved_requests if req.media_type == 'tv']
            if tv_requests:
                tv_stats = await self._check_sonarr_downloads(tv_requests)
                stats['checked'] += tv_stats['checked']
                stats['updated_to_downloading'] += tv_stats['updated_to_downloading']
                stats['updated_to_downloaded'] += tv_stats['updated_to_downloaded']
                stats['errors'] += tv_stats['errors']
            
            print(f"✅ Download status check completed: {stats}")
            return stats
            
        except Exception as e:
            print(f"❌ Error in download status check: {e}")
            stats['errors'] += 1
            return stats
    
    async def _check_radarr_downloads(self, movie_requests: List[MediaRequest]) -> Dict[str, int]:
        """Check Radarr instances for movie download status"""
        stats = {'checked': 0, 'updated_to_downloading': 0, 'updated_to_downloaded': 0, 'errors': 0}
        
        # Get all enabled Radarr instances
        radarr_instances = list(self.session.exec(
            select(ServiceInstance).where(
                ServiceInstance.service_type == ServiceType.RADARR,
                ServiceInstance.is_enabled == True
            )
        ))
        
        if not radarr_instances:
            print("⚠️ No enabled Radarr instances found")
            return stats
        
        for instance in radarr_instances:
            try:
                instance_stats = await self._check_radarr_instance(instance, movie_requests)
                stats['checked'] += instance_stats['checked']
                stats['updated_to_downloading'] += instance_stats['updated_to_downloading']
                stats['updated_to_downloaded'] += instance_stats['updated_to_downloaded']
                stats['errors'] += instance_stats['errors']
            except Exception as e:
                print(f"❌ Error checking Radarr instance {instance.name}: {e}")
                stats['errors'] += 1
        
        return stats
    
    async def _check_radarr_instance(self, instance: ServiceInstance, movie_requests: List[MediaRequest]) -> Dict[str, int]:
        """Check a specific Radarr instance for movie download status"""
        stats = {'checked': 0, 'updated_to_downloading': 0, 'updated_to_downloaded': 0, 'errors': 0}
        
        if not instance.url or not instance.api_key:
            print(f"⚠️ Radarr instance {instance.name} missing URL or API key")
            return stats
        
        headers = {
            'X-Api-Key': instance.api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            # Get queue (downloading items)
            queue_response = requests.get(
                f"{instance.url.rstrip('/')}/api/v3/queue",
                headers=headers,
                timeout=10
            )
            queue_response.raise_for_status()
            queue_items = queue_response.json().get('records', [])
            
            # Get all movies in Radarr
            movies_response = requests.get(
                f"{instance.url.rstrip('/')}/api/v3/movie",
                headers=headers,
                timeout=10
            )
            movies_response.raise_for_status()
            radarr_movies = movies_response.json()
            
            # Create lookup dictionaries
            queue_tmdb_ids = {item.get('movie', {}).get('tmdbId') for item in queue_items if item.get('movie', {}).get('tmdbId')}
            downloaded_tmdb_ids = {
                movie.get('tmdbId') for movie in radarr_movies 
                if movie.get('tmdbId') and movie.get('hasFile', False)
            }
            
            # Check each movie request
            for request in movie_requests:
                stats['checked'] += 1
                
                if request.tmdb_id in downloaded_tmdb_ids:
                    # Movie is downloaded - mark as available
                    if request.status != RequestStatus.AVAILABLE:
                        request.status = RequestStatus.AVAILABLE
                        request.updated_at = datetime.utcnow()
                        self.session.add(request)
                        stats['updated_to_downloaded'] += 1
                        print(f"✅ Movie '{request.title}' marked as available (downloaded)")
                
                elif request.tmdb_id in queue_tmdb_ids:
                    # Movie is in download queue but we don't have downloading status
                    print(f"📥 Movie '{request.title}' is downloading in Radarr")
                    # Could add downloading status here if it existed in the enum
                
        except Exception as e:
            print(f"❌ Error checking Radarr instance {instance.name}: {e}")
            stats['errors'] += 1
        
        return stats
    
    async def _check_sonarr_downloads(self, tv_requests: List[MediaRequest]) -> Dict[str, int]:
        """Check Sonarr instances for TV show download status"""
        stats = {'checked': 0, 'updated_to_downloading': 0, 'updated_to_downloaded': 0, 'errors': 0}
        
        # Get all enabled Sonarr instances
        sonarr_instances = list(self.session.exec(
            select(ServiceInstance).where(
                ServiceInstance.service_type == ServiceType.SONARR,
                ServiceInstance.is_enabled == True
            )
        ))
        
        if not sonarr_instances:
            print("⚠️ No enabled Sonarr instances found")
            return stats
        
        for instance in sonarr_instances:
            try:
                instance_stats = await self._check_sonarr_instance(instance, tv_requests)
                stats['checked'] += instance_stats['checked']
                stats['updated_to_downloading'] += instance_stats['updated_to_downloading']
                stats['updated_to_downloaded'] += instance_stats['updated_to_downloaded']
                stats['errors'] += instance_stats['errors']
            except Exception as e:
                print(f"❌ Error checking Sonarr instance {instance.name}: {e}")
                stats['errors'] += 1
        
        return stats
    
    async def _check_sonarr_instance(self, instance: ServiceInstance, tv_requests: List[MediaRequest]) -> Dict[str, int]:
        """Check a specific Sonarr instance for TV show download status"""
        stats = {'checked': 0, 'updated_to_downloading': 0, 'updated_to_downloaded': 0, 'errors': 0}
        
        if not instance.url or not instance.api_key:
            print(f"⚠️ Sonarr instance {instance.name} missing URL or API key")
            return stats
        
        headers = {
            'X-Api-Key': instance.api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            # Get queue (downloading items)
            queue_response = requests.get(
                f"{instance.url.rstrip('/')}/api/v3/queue",
                headers=headers,
                timeout=10
            )
            queue_response.raise_for_status()
            queue_items = queue_response.json().get('records', [])
            
            # Get all series in Sonarr
            series_response = requests.get(
                f"{instance.url.rstrip('/')}/api/v3/series",
                headers=headers,
                timeout=10
            )
            series_response.raise_for_status()
            sonarr_series = series_response.json()
            
            # Create lookup dictionaries
            queue_tvdb_ids = {item.get('series', {}).get('tvdbId') for item in queue_items if item.get('series', {}).get('tvdbId')}
            
            # For TV shows, check if they have any files (episodes)
            available_tvdb_ids = set()
            for series in sonarr_series:
                tvdb_id = series.get('tvdbId')
                if tvdb_id and series.get('statistics', {}).get('episodeFileCount', 0) > 0:
                    available_tvdb_ids.add(tvdb_id)
            
            # Check each TV request
            for request in tv_requests:
                stats['checked'] += 1
                
                # Note: We need to map TMDB ID to TVDB ID for TV shows
                # This is a simplified check - in reality you'd need to look up the TVDB ID
                # For now, we'll check if the TMDB ID is in Sonarr directly
                
                # Try to find the series by TMDB ID (some Sonarr versions support this)
                series_found = None
                for series in sonarr_series:
                    # Check if series has this TMDB ID (newer Sonarr versions)
                    if series.get('tmdbId') == request.tmdb_id:
                        series_found = series
                        break
                
                if series_found:
                    episode_file_count = series_found.get('statistics', {}).get('episodeFileCount', 0)
                    if episode_file_count > 0:
                        # TV show has episodes - mark as available
                        if request.status != RequestStatus.AVAILABLE:
                            request.status = RequestStatus.AVAILABLE
                            request.updated_at = datetime.utcnow()
                            self.session.add(request)
                            stats['updated_to_downloaded'] += 1
                            print(f"✅ TV show '{request.title}' marked as available ({episode_file_count} episodes)")
                    else:
                        # Series exists but no episodes yet
                        print(f"📥 TV show '{request.title}' added to Sonarr but no episodes downloaded yet")
                
        except Exception as e:
            print(f"❌ Error checking Sonarr instance {instance.name}: {e}")
            stats['errors'] += 1
        
        return stats
    
    def commit_changes(self):
        """Commit any status changes to the database"""
        try:
            self.session.commit()
            print("✅ Download status changes committed to database")
        except Exception as e:
            print(f"❌ Error committing download status changes: {e}")
            self.session.rollback()
            raise


# Standalone function for background job usage
async def check_download_status() -> Dict[str, Any]:
    """
    Standalone function to check download status.
    This can be called by the background job scheduler.
    """
    service = DownloadStatusService()
    try:
        result = await service.check_download_status()
        service.commit_changes()
        return result
    except Exception as e:
        print(f"❌ Error in download status check: {e}")
        return {
            'checked': 0,
            'updated_to_downloading': 0,
            'updated_to_downloaded': 0,
            'errors': 1,
            'error_message': str(e)
        }
    finally:
        service.session.close()