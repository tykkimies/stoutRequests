import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor
import threading
import time

from ..services.plex_sync_service import PlexSyncService
from ..core.database import get_session


class BackgroundJobManager:
    """
    Simple background job manager for handling async tasks like library sync.
    """
    
    def __init__(self):
        self.running = False
        self.scheduler_running = False
        self.last_library_sync: Optional[datetime] = None
        self.last_download_check: Optional[datetime] = None
        self.download_status_interval = 120  # 2 minutes in seconds
        self.library_sync_interval = 3600  # 1 hour in seconds
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._lock = threading.Lock()
        self._scheduler_thread = None
        
        # Job status tracking
        self.jobs = {
            'library_sync': {
                'name': 'Library Sync',
                'description': 'Syncs Plex library to local database',
                'last_run': None,
                'next_run': None,
                'running': False,
                'interval_seconds': self.library_sync_interval,
                'stats': {},
                'enabled': False,  # Auto-scheduling DISABLED by default to prevent overwhelming site
                'auto_run': False
            },
            'download_status_check': {
                'name': 'Download Status Check',
                'description': 'Checks Radarr/Sonarr for download status updates',
                'last_run': None,
                'next_run': None,
                'running': False,
                'interval_seconds': self.download_status_interval,
                'stats': {},
                'enabled': False,  # Auto-scheduling DISABLED by default to prevent overwhelming site
                'auto_run': False
            }
        }
        
        # Calculate initial next run times
        self._calculate_next_runs()
    
    def start(self):
        """Start the background job manager and scheduler"""
        with self._lock:
            if not self.running:
                self.running = True
                self.scheduler_running = True
                
                # Start the scheduler thread
                self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
                self._scheduler_thread.start()
                
                print("🚀 Background job manager and scheduler started")
    
    def stop(self):
        """Stop the background job manager and scheduler"""
        with self._lock:
            if self.running:
                self.running = False
                self.scheduler_running = False
                
                # Wait for scheduler thread to finish
                if self._scheduler_thread and self._scheduler_thread.is_alive():
                    self._scheduler_thread.join(timeout=5)
                
                self._executor.shutdown(wait=True)
                print("🛑 Background job manager and scheduler stopped")
    
    def _calculate_next_runs(self):
        """Calculate next run times for all jobs"""
        now = datetime.utcnow()
        with self._lock:
            for job_name, job in self.jobs.items():
                if job.get('enabled', True) and job.get('auto_run', True):
                    if job['last_run']:
                        job['next_run'] = job['last_run'] + timedelta(seconds=job['interval_seconds'])
                    else:
                        # First run - schedule for a few seconds from now to allow startup
                        job['next_run'] = now + timedelta(seconds=30)
                else:
                    job['next_run'] = None
    
    def _scheduler_loop(self):
        """Main scheduler loop that runs in a separate thread"""
        print("🕐 Scheduler loop started")
        
        while self.scheduler_running:
            try:
                self._check_and_run_scheduled_jobs()
                time.sleep(10)  # Check every 10 seconds
            except Exception as e:
                print(f"❌ Error in scheduler loop: {e}")
                time.sleep(30)  # Back off on error
        
        print("🕐 Scheduler loop stopped")
    
    def _check_and_run_scheduled_jobs(self):
        """Check if any jobs need to run and execute them"""
        now = datetime.utcnow()
        
        with self._lock:
            jobs_to_run = []
            for job_name, job in self.jobs.items():
                if (job.get('enabled', True) and 
                    job.get('auto_run', True) and 
                    not job.get('running', False) and 
                    job.get('next_run') and 
                    now >= job['next_run']):
                    jobs_to_run.append(job_name)
        
        # Run jobs outside of the lock to avoid blocking
        for job_name in jobs_to_run:
            print(f"⏰ Auto-running scheduled job: {job_name}")
            # Submit job to thread pool since we're not in an async context
            self._executor.submit(self._run_job_sync, job_name)
    
    def _trigger_status_update(self, job_name: str):
        """Trigger HTMX status update for connected clients"""
        try:
            # For now, we'll implement a simple approach that works with the existing system
            # In a full implementation, this would use WebSockets or Server-Sent Events
            # to push updates to connected clients
            
            # Get the current job status
            job_status = self.get_job_status(job_name)
            
            # Log the status change for debugging
            if job_status.get('running'):
                print(f"🔄 Job '{job_name}' started - clients should be notified")
            else:
                print(f"✅ Job '{job_name}' completed - clients should be notified")
            
            # TODO: In a future enhancement, implement WebSocket or SSE push notifications
            # For now, the admin interface will need to poll for updates or use HTMX intervals
            
        except Exception as e:
            print(f"❌ Error triggering status update for {job_name}: {e}")
    
    def _run_job_sync(self, job_name: str):
        """Run a specific job synchronously (called from scheduler thread)"""
        try:
            # Create new event loop for this job
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                if job_name == 'library_sync':
                    result = loop.run_until_complete(self.trigger_library_sync())
                    print(f"✅ Scheduled library sync completed: {result.get('success', False)}")
                elif job_name == 'download_status_check':
                    result = loop.run_until_complete(self.trigger_download_status_check())
                    print(f"✅ Scheduled download status check completed: {result.get('success', False)}")
                else:
                    print(f"⚠️ Unknown job type: {job_name}")
            finally:
                loop.close()
                
        except Exception as e:
            print(f"❌ Error running scheduled job {job_name}: {e}")
    
    async def _run_job_async(self, job_name: str):
        """Run a specific job asynchronously"""
        try:
            if job_name == 'library_sync':
                result = await self.trigger_library_sync()
                print(f"✅ Scheduled library sync completed: {result.get('success', False)}")
            elif job_name == 'download_status_check':
                result = await self.trigger_download_status_check()
                print(f"✅ Scheduled download status check completed: {result.get('success', False)}")
            else:
                print(f"⚠️ Unknown job type: {job_name}")
        except Exception as e:
            print(f"❌ Error running scheduled job {job_name}: {e}")
    
    def update_job_schedule(self, job_name: str, interval_seconds: int = None, enabled: bool = None):
        """Update job scheduling configuration"""
        with self._lock:
            if job_name in self.jobs:
                job = self.jobs[job_name]
                if interval_seconds is not None:
                    job['interval_seconds'] = interval_seconds
                if enabled is not None:
                    job['enabled'] = enabled
                    job['auto_run'] = enabled
                
                # Recalculate next run time
                if job.get('enabled', True) and job.get('auto_run', True):
                    if job['last_run']:
                        job['next_run'] = job['last_run'] + timedelta(seconds=job['interval_seconds'])
                    else:
                        job['next_run'] = datetime.utcnow() + timedelta(seconds=30)
                else:
                    job['next_run'] = None
                
                print(f"📅 Updated schedule for {job_name}: interval={interval_seconds}s, enabled={enabled}")
                return True
        return False
    
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
        
        # Trigger HTMX update to show job started
        self._trigger_status_update('library_sync')
        
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
                # Update next run time if auto-scheduling is enabled
                if self.jobs['library_sync'].get('enabled', True) and self.jobs['library_sync'].get('auto_run', True):
                    self.jobs['library_sync']['next_run'] = datetime.utcnow() + timedelta(seconds=self.jobs['library_sync']['interval_seconds'])
            
            # Trigger HTMX update for any connected clients
            self._trigger_status_update('library_sync')
            
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
        This checks Radarr/Sonarr download queues and updates request statuses.
        """
        with self._lock:
            is_running = self.jobs['download_status_check']['running']
        
        if is_running:
            print("⚠️ Download status check already running - rejecting new check request")
            return {
                'success': False,
                'message': 'Download status check already running',
                'job_id': None
            }
        
        # Mark job as running
        with self._lock:
            self.jobs['download_status_check']['running'] = True
            self.jobs['download_status_check']['last_run'] = datetime.utcnow()
        
        try:
            print("🔄 Starting background download status check...")
            
            # Run the download status check in the thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._executor,
                self._run_download_status_check_sync
            )
            
            # Update job status
            with self._lock:
                self.jobs['download_status_check']['stats'] = result
                self.last_download_check = datetime.utcnow()
                # Update next run time if auto-scheduling is enabled
                if self.jobs['download_status_check'].get('enabled', True) and self.jobs['download_status_check'].get('auto_run', True):
                    self.jobs['download_status_check']['next_run'] = datetime.utcnow() + timedelta(seconds=self.jobs['download_status_check']['interval_seconds'])
            
            # Trigger HTMX update for any connected clients
            self._trigger_status_update('download_status_check')
            
            print(f"✅ Background download status check completed: {result}")
            
            return {
                'success': True,
                'message': 'Download status check completed successfully',
                'stats': result
            }
            
        except Exception as e:
            print(f"❌ Error in background download status check: {e}")
            return {
                'success': False,
                'message': f'Download status check failed: {str(e)}',
                'error': str(e)
            }
        finally:
            # Mark job as no longer running
            with self._lock:
                self.jobs['download_status_check']['running'] = False
    
    def _run_download_status_check_sync(self) -> Dict[str, Any]:
        """
        Synchronous wrapper for the async download status check.
        This runs in a thread pool.
        """
        try:
            print("🔄 Creating new event loop for background download status check...")
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                print("🔄 Starting actual download status check...")
                # Import and run the download status check
                from .download_status_service import check_download_status
                result = loop.run_until_complete(check_download_status())
                
                print(f"🔄 Download status check completed with result: {result}")
                return result
            finally:
                loop.close()
                
        except Exception as e:
            print(f"❌ Error in download status check thread: {e}")
            import traceback
            traceback.print_exc()
            return {
                'checked': 0,
                'updated_to_downloading': 0,
                'updated_to_downloaded': 0,
                'errors': 1,
                'error_message': str(e)
            }


# Global instance
background_jobs = BackgroundJobManager()


# Functions for compatibility with existing admin code
async def trigger_library_sync() -> Dict[str, Any]:
    """Trigger library sync job"""
    return await background_jobs.trigger_library_sync()


async def trigger_download_status_check() -> Dict[str, Any]:
    """Trigger download status check job"""
    return await background_jobs.trigger_download_status_check()


# Auto-start the manager - DISABLED to prevent overwhelming site
# background_jobs.start()  # User must manually enable scheduling in admin panel