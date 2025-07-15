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
        self.download_status_interval = 300  # 5 minutes
        self.last_download_check = None
    
    async def start(self):
        """Start the background job service"""
        if self.running:
            logger.warning("Background jobs already running")
            return
        
        self.running = True
        logger.info("🚀 Starting background job service...")
        
        # Start the main job loop
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
                
                # Sleep for 30 seconds before next check
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