import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor
import threading

from ..services.plex_sync_service import PlexSyncService
from ..core.database import get_session


class BackgroundJobManager:
    """
    Simple background job manager for handling async tasks like library sync.
    """
    
    def __init__(self):
        self.running = False
        self.last_library_sync: Optional[datetime] = None
        self.last_download_check: Optional[datetime] = None
        self.download_status_interval = 120  # 2 minutes in seconds
        self.library_sync_interval = 3600  # 1 hour in seconds
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._lock = threading.Lock()
        
        # Job status tracking
        self.jobs = {
            'library_sync': {
                'name': 'Library Sync',
                'description': 'Syncs Plex library to local database',
                'last_run': None,
                'next_run': None,
                'running': False,
                'interval_seconds': self.library_sync_interval,
                'stats': {}
            },
            'download_status_check': {
                'name': 'Download Status Check',
                'description': 'Checks Radarr/Sonarr for download status updates',
                'last_run': None,
                'next_run': None,
                'running': False,
                'interval_seconds': self.download_status_interval,
                'stats': {}
            }
        }
    
    def start(self):
        """Start the background job manager"""
        with self._lock:
            if not self.running:
                self.running = True
                print("🚀 Background job manager started")
    
    def stop(self):
        """Stop the background job manager"""
        with self._lock:
            if self.running:
                self.running = False
                self._executor.shutdown(wait=True)
                print("🛑 Background job manager stopped")
    
    def get_job_status(self, job_name: str) -> Dict[str, Any]:
        """Get status of a specific job"""
        with self._lock:
            if job_name in self.jobs:
                job = self.jobs[job_name].copy()
                
                # Calculate next run time if we have a last run
                if job['last_run'] and job['interval_seconds']:
                    job['next_run'] = job['last_run'] + timedelta(seconds=job['interval_seconds'])
                
                return job
            
            return {}
    
    def get_all_jobs_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all jobs"""
        return {name: self.get_job_status(name) for name in self.jobs.keys()}
    
    async def trigger_library_sync(self) -> Dict[str, Any]:
        """
        Manually trigger a library sync job.
        This runs in the background and doesn't block the web request.
        """
        with self._lock:
            is_running = self.jobs['library_sync']['running']
        
        if is_running:
            print("⚠️ Library sync already running - rejecting new sync request")
            return {
                'success': False,
                'message': 'Library sync already running',
                'job_id': None
            }
        
        # Mark job as running
        with self._lock:
            self.jobs['library_sync']['running'] = True
            self.jobs['library_sync']['last_run'] = datetime.utcnow()
        
        try:
            print("🔄 Starting background library sync...")
            
            # Run the sync in the thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._executor,
                self._run_library_sync_sync
            )
            
            # Update job status
            with self._lock:
                self.jobs['library_sync']['stats'] = result
                self.last_library_sync = datetime.utcnow()
            
            print(f"✅ Background library sync completed: {result}")
            
            return {
                'success': True,
                'message': 'Library sync started successfully',
                'stats': result
            }
            
        except Exception as e:
            print(f"❌ Error in background library sync: {e}")
            return {
                'success': False,
                'message': f'Library sync failed: {str(e)}',
                'error': str(e)
            }
        finally:
            # Mark job as no longer running
            with self._lock:
                self.jobs['library_sync']['running'] = False
    
    def _run_library_sync_sync(self) -> Dict[str, Any]:
        """
        Synchronous wrapper for the async library sync.
        This runs in a thread pool.
        """
        try:
            print("🔄 Creating new event loop for background sync...")
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                print("🔄 Creating database session for background sync...")
                # Create sync service with a fresh session to ensure we get latest settings
                from sqlmodel import Session
                from ..core.database import engine
                
                with Session(engine) as session:
                    print("🔄 Initializing PlexSyncService...")
                    sync_service = PlexSyncService(session)
                    
                    # Refresh session to ensure we get latest data
                    session.expire_all()
                    
                    print("🔄 Starting actual library sync...")
                    result = loop.run_until_complete(sync_service.sync_library())
                    
                    print(f"🔄 Sync completed with result: {result}")
                    return result
            finally:
                loop.close()
                
        except Exception as e:
            print(f"❌ Error in sync thread: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}
    
    async def trigger_download_status_check(self) -> Dict[str, Any]:
        """
        Manually trigger a download status check job.
        This is a placeholder - the actual implementation would check Radarr/Sonarr.
        """
        if self.jobs['download_status_check']['running']:
            return {
                'success': False,
                'message': 'Download status check already running'
            }
        
        # Mark job as running
        with self._lock:
            self.jobs['download_status_check']['running'] = True
            self.jobs['download_status_check']['last_run'] = datetime.utcnow()
        
        try:
            print("🔄 Starting download status check...")
            
            # Placeholder implementation
            await asyncio.sleep(1)  # Simulate work
            
            stats = {
                'checked': 0,
                'updated_to_downloading': 0,
                'updated_to_downloaded': 0,
                'errors': 0
            }
            
            # Update job status
            with self._lock:
                self.jobs['download_status_check']['stats'] = stats
                self.last_download_check = datetime.utcnow()
            
            print(f"✅ Download status check completed: {stats}")
            
            return {
                'success': True,
                'message': 'Download status check completed',
                'stats': stats
            }
            
        except Exception as e:
            print(f"❌ Error in download status check: {e}")
            return {
                'success': False,
                'message': f'Download status check failed: {str(e)}',
                'error': str(e)
            }
        finally:
            # Mark job as no longer running
            with self._lock:
                self.jobs['download_status_check']['running'] = False


# Global instance
background_jobs = BackgroundJobManager()


# Functions for compatibility with existing admin code
async def trigger_library_sync() -> Dict[str, Any]:
    """Trigger library sync job"""
    return await background_jobs.trigger_library_sync()


async def trigger_download_status_check() -> Dict[str, Any]:
    """Trigger download status check job"""
    return await background_jobs.trigger_download_status_check()


# Auto-start the manager
background_jobs.start()