"""
Background job system for periodic tasks

This service runs periodic tasks as fallback to webhooks:
- Download status checking (every 5 minutes)
- Cleanup tasks (as needed)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from sqlmodel import Session

from ..core.database import engine
from ..services.download_status_service import DownloadStatusService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BackgroundJobService:
    def __init__(self):
        self.running = False
        self.download_status_interval = 120  # 2 minutes (like Jellyseerr)
        self.last_download_check = None
    
    async def start(self):
        """Start the background job service"""
        if self.running:
            logger.warning("Background jobs already running")
            return
        
        self.running = True
        logger.info("🚀 Starting background job service...")
        logger.info("✅ Background jobs enabled (Jellyseerr-style periodic polling)")
        
        # Start the main job loop with Jellyseerr-style polling (2 minutes)
        asyncio.create_task(self._job_loop())
    
    async def stop(self):
        """Stop the background job service"""
        self.running = False
        logger.info("🛑 Stopping background job service...")
    
    async def _job_loop(self):
        """Main background job loop"""
        while self.running:
            try:
                # Check if we need to run download status check
                if self._should_check_download_status():
                    await self._run_download_status_check()
                
                # Process pending service integrations
                await self._process_pending_service_integrations()
                
                # Sleep for 30 seconds before next check (lighter polling)
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"❌ Error in background job loop: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    def _should_check_download_status(self) -> bool:
        """Check if it's time to run download status check"""
        if not self.last_download_check:
            return True
        
        time_since_last = datetime.utcnow() - self.last_download_check
        return time_since_last.total_seconds() >= self.download_status_interval
    
    async def _run_download_status_check(self):
        """Run the download status check job"""
        try:
            logger.info("🔄 Running background download status check...")
            
            with Session(engine) as session:
                service = DownloadStatusService(session)
                stats = await service.check_download_statuses()
                
                logger.info(f"✅ Background download status check completed: {stats}")
                self.last_download_check = datetime.utcnow()
                
        except Exception as e:
            logger.error(f"❌ Error in download status check: {e}")
    
    async def _process_pending_service_integrations(self):
        """Process requests that are approved but pending service integration"""
        try:
            with Session(engine) as session:
                from ..models.media_request import MediaRequest, RequestStatus, MediaType
                from sqlmodel import select
                
                # Find approved requests that don't have service integration yet
                # (no radarr_id for movies or sonarr_id for TV shows)
                statement = select(MediaRequest).where(
                    MediaRequest.status == RequestStatus.APPROVED,
                    ((MediaRequest.media_type == MediaType.MOVIE) & (MediaRequest.radarr_id.is_(None))) |
                    ((MediaRequest.media_type == MediaType.TV) & (MediaRequest.sonarr_id.is_(None)))
                )
                pending_requests = session.exec(statement).all()
                
                if pending_requests:
                    logger.info(f"🔄 Processing {len(pending_requests)} pending service integrations...")
                    
                    for request in pending_requests:
                        await trigger_service_integration(request.id)
                        
                        # Small delay between requests to avoid overwhelming services
                        await asyncio.sleep(1)
                        
        except Exception as e:
            logger.error(f"❌ Error processing pending service integrations: {e}")
    
    async def run_download_status_check_now(self) -> Dict[str, int]:
        """Manually trigger download status check (for testing)"""
        logger.info("🔧 Manual download status check triggered")
        
        with Session(engine) as session:
            service = DownloadStatusService(session)
            return await service.check_download_statuses()


# Global instance
background_jobs = BackgroundJobService()


async def start_background_jobs():
    """Start background jobs (called from app startup)"""
    await background_jobs.start()


async def stop_background_jobs():
    """Stop background jobs (called from app shutdown)"""
    await background_jobs.stop()


async def trigger_download_status_check() -> Dict[str, int]:
    """Manually trigger download status check"""
    return await background_jobs.run_download_status_check_now()


async def trigger_service_integration(request_id: int):
    """Trigger immediate service integration for a specific request"""
    try:
        logger.info(f"🔧 Triggering service integration for request {request_id}")
        
        with Session(engine) as session:
            from ..models.media_request import MediaRequest, RequestStatus, MediaType
            from ..services.radarr_service import RadarrService  
            from ..services.sonarr_service import SonarrService
            from sqlmodel import select
            
            # Get the request
            statement = select(MediaRequest).where(MediaRequest.id == request_id)
            media_request = session.exec(statement).first()
            
            if not media_request:
                logger.error(f"❌ Request {request_id} not found")
                return
            
            if media_request.status != RequestStatus.APPROVED:
                logger.warning(f"⚠️ Request {request_id} is not approved")
                return
            
            # Check if service integration is already done
            if media_request.media_type == MediaType.MOVIE and media_request.radarr_id:
                logger.info(f"✅ Movie already integrated with Radarr (ID: {media_request.radarr_id})")
                return
            elif media_request.media_type == MediaType.TV and media_request.sonarr_id:
                logger.info(f"✅ TV show already integrated with Sonarr (ID: {media_request.sonarr_id})")
                return
            
            success = False
            
            try:
                if media_request.media_type == MediaType.MOVIE:
                    logger.info(f"📽️ Adding movie to Radarr: {media_request.title}")
                    radarr_service = RadarrService(session)
                    radarr_result = radarr_service.add_movie(media_request.tmdb_id, user_id=media_request.user_id)
                    if radarr_result:
                        media_request.radarr_id = radarr_result.get('id')
                        success = True
                        logger.info(f"✅ Movie added to Radarr with ID {media_request.radarr_id}")
                    else:
                        logger.error(f"❌ Failed to add movie to Radarr")
                        
                elif media_request.media_type == MediaType.TV:
                    logger.info(f"📺 Adding TV series to Sonarr: {media_request.title}")
                    sonarr_service = SonarrService(session)
                    sonarr_result = sonarr_service.add_series(media_request.tmdb_id, user_id=media_request.user_id)
                    if sonarr_result:
                        media_request.sonarr_id = sonarr_result.get('id')
                        success = True
                        logger.info(f"✅ TV series added to Sonarr with ID {media_request.sonarr_id}")
                    else:
                        logger.error(f"❌ Failed to add TV series to Sonarr")
                
                media_request.updated_at = datetime.utcnow()
                session.add(media_request)
                session.commit()
                
                if success:
                    logger.info(f"✅ Service integration completed for request {request_id}")
                else:
                    logger.error(f"❌ Service integration failed for request {request_id}")
                    
            except Exception as e:
                logger.error(f"❌ Error during service integration for request {request_id}: {e}")
                # Request stays APPROVED with no service ID, so it can be retried
                
    except Exception as e:
        logger.error(f"❌ Fatal error in service integration for request {request_id}: {e}")