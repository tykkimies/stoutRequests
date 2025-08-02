import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any, List
from concurrent.futures import ThreadPoolExecutor
import threading
import time

from ..services.plex_sync_service import PlexSyncService
from ..core.database import get_session
from ..models.job_execution import JobExecution

def get_utc_now():
    """Get current UTC time with timezone awareness"""
    return datetime.now(timezone.utc)

def format_datetime_local(dt):
    """Format a UTC datetime for local display"""
    if dt is None:
        return "Never"
    
    # Ensure datetime is timezone-aware (convert from naive UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to local time for display (system local time)
    try:
        # Try to use zoneinfo for Python 3.9+ (built-in)
        from zoneinfo import ZoneInfo
        local_tz = ZoneInfo('America/New_York')  # TODO: Make this configurable
        local_dt = dt.astimezone(local_tz)
        return local_dt.strftime('%Y-%m-%d %H:%M:%S %Z')
    except ImportError:
        # Fallback: just show UTC time with clear label
        return dt.strftime('%Y-%m-%d %H:%M:%S UTC')

def format_datetime_utc(dt):
    """Format a datetime as UTC for consistent storage/comparison"""
    if dt is None:
        return None
    
    # Ensure datetime is timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    return dt.astimezone(timezone.utc)

# tracker:task("Add accessibility to modal")
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
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bg_job")
        self._lock = threading.Lock()
        self._scheduler_thread = None
        
        # Job status tracking - initialize jobs then load persisted settings
        self.jobs = {}
        self._initialize_jobs()
        self._load_job_settings()
        
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
        
        # Shutdown the thread pool executor gracefully
        if self._executor:
            print("🛑 Shutting down thread pool executor...")
            self._executor.shutdown(wait=True, cancel_futures=True)
            print("✅ Thread pool executor shutdown complete")
    
    def restart(self):
        """Restart the scheduler with a fresh executor"""
        print("🔄 Restarting background job scheduler...")
        
        # Stop current scheduler
        self.stop()
        
        # Create a new executor
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bg_job")
        
        # Start fresh
        self.start()
        
        print("✅ Background job scheduler restarted successfully")
    
    def _calculate_next_runs(self):
        """Calculate next run times for all jobs"""
        now = get_utc_now()
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
                # Check if we're shutting down before doing work
                if not self.scheduler_running:
                    break
                    
                self._check_and_run_scheduled_jobs()
                
                # Sleep in smaller increments to respond faster to shutdown
                for _ in range(10):  # 10 x 1 second = 10 seconds total
                    if not self.scheduler_running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                error_msg = str(e).lower()
                if "interpreter shutdown" in error_msg or "cannot schedule new futures" in error_msg:
                    print(f"🛑 Scheduler shutting down due to interpreter shutdown")
                    break
                    
                print(f"❌ Error in scheduler loop: {e}")
                # Back off on error, but check shutdown status
                for _ in range(30):  # 30 x 1 second = 30 seconds total
                    if not self.scheduler_running:
                        break
                    time.sleep(1)
        
        print("🕐 Scheduler loop stopped")
    
    def _check_and_run_scheduled_jobs(self):
        """Check if any jobs need to run and execute them"""
        now = get_utc_now()
        
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
            # Check if we're still running before submitting jobs
            if not self.scheduler_running:
                print(f"🛑 Scheduler shutting down, skipping job: {job_name}")
                break
                
            print(f"⏰ Auto-running scheduled job: {job_name}")
            # Submit job to thread pool since we're not in an async context
            try:
                self._executor.submit(self._run_job_sync, job_name)
            except RuntimeError as e:
                if "cannot schedule new futures" in str(e).lower():
                    print(f"🛑 Cannot schedule new job {job_name} - executor shutting down")
                    break
                else:
                    raise
    
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
        start_time = get_utc_now()
        loop = None
        try:
            # Check if scheduler is still running before creating event loop
            if not self.scheduler_running:
                print(f"⚠️ Scheduler shutting down, skipping job: {job_name}")
                return
            
            # Create new event loop for this job
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                if job_name == 'library_sync':
                    # Run the job directly without trigger method to avoid double execution tracking
                    result = loop.run_until_complete(self._run_library_sync_async())
                    success = result.get('success', True) if isinstance(result, dict) else not result.get('error')
                    print(f"✅ Scheduled library sync completed: {success}")
                elif job_name == 'download_status_check':
                    # Run the job directly without trigger method to avoid double execution tracking
                    result = loop.run_until_complete(self._run_download_status_check_async())
                    success = result.get('success', True) if isinstance(result, dict) else not result.get('error')
                    print(f"✅ Scheduled download status check completed: {success}")
                elif job_name == 'request_submission':
                    # Run the job directly without trigger method to avoid double execution tracking
                    result = loop.run_until_complete(self._process_approved_requests())
                    success = result.get('success', True) if isinstance(result, dict) else not result.get('error')
                    print(f"✅ Scheduled request submission completed: {success}")
                else:
                    print(f"⚠️ Unknown job type: {job_name}")
                    result = {'success': False, 'error': f'Unknown job type: {job_name}'}
                    success = False
                
                # Only create execution record if scheduler is still running
                if self.scheduler_running:
                    # Create completed job execution record only after job finishes
                    self._create_completed_job_execution(
                        job_name=job_name,
                        triggered_by="scheduler",
                        started_at=start_time,
                        completed_at=get_utc_now(),
                        success=success,
                        result_data=result if isinstance(result, dict) else {'result': str(result)},
                        error_message=result.get('error') if isinstance(result, dict) else None
                    )
                    
            finally:
                # Safely close the event loop
                if loop and not loop.is_closed():
                    try:
                        loop.close()
                    except Exception as e:
                        print(f"⚠️ Error closing event loop: {e}")
                
        except Exception as e:
            print(f"❌ Error running scheduled job {job_name}: {e}")
            # Only create execution record if scheduler is still running and it's not a shutdown error
            if self.scheduler_running and "interpreter shutdown" not in str(e).lower():
                try:
                    # Create failed job execution record
                    self._create_completed_job_execution(
                        job_name=job_name,
                        triggered_by="scheduler", 
                        started_at=start_time,
                        completed_at=get_utc_now(),
                        success=False,
                        error_message=str(e)
                    )
                except Exception as db_error:
                    print(f"⚠️ Error creating job execution record during shutdown: {db_error}")
        finally:
            # Safely close the event loop if it wasn't closed in the inner finally
            if loop and not loop.is_closed():
                try:
                    loop.close()
                except Exception as e:
                    print(f"⚠️ Error closing event loop in outer finally: {e}")
    
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
                        job['next_run'] = get_utc_now() + timedelta(seconds=30)
                else:
                    job['next_run'] = None
                
                print(f"📅 Updated schedule for {job_name}: interval={interval_seconds}s, enabled={enabled}")
                
                # Persist the updated settings to database
                self._save_job_settings()
                
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
    
    async def trigger_library_sync(self, triggered_by: str = "manual") -> Dict[str, Any]:
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
        
        # Create job execution record
        execution_id = self._create_job_execution('library_sync', triggered_by)
        
        # Mark job as running
        with self._lock:
            self.jobs['library_sync']['running'] = True
            self.jobs['library_sync']['last_run'] = get_utc_now()
        
        # Trigger HTMX update to show job started
        self._trigger_status_update('library_sync')
        
        try:
            print("🔄 Starting background library sync...")
            
            # Run the sync in the thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            
            # Add timeout to prevent hanging
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        self._executor,
                        self._run_library_sync_sync
                    ),
                    timeout=600  # 10 minute timeout
                )
            except asyncio.TimeoutError:
                print("❌ Library sync timed out after 10 minutes")
                result = {'error': 'Library sync timed out after 10 minutes'}
            
            # Determine success based on result
            success = result.get('success', True) if isinstance(result, dict) else not result.get('error')
            
            # Update job execution record
            self._update_job_execution(
                execution_id, 
                success=success, 
                result_data=result if isinstance(result, dict) else {'result': str(result)},
                error_message=result.get('error') if isinstance(result, dict) else None
            )
            
            # Update job status
            with self._lock:
                self.jobs['library_sync']['stats'] = result
                self.last_library_sync = get_utc_now()
                # Update next run time if auto-scheduling is enabled
                if self.jobs['library_sync'].get('enabled', True) and self.jobs['library_sync'].get('auto_run', True):
                    self.jobs['library_sync']['next_run'] = get_utc_now() + timedelta(seconds=self.jobs['library_sync']['interval_seconds'])
            
            # Trigger HTMX update for any connected clients
            self._trigger_status_update('library_sync')
            
            print(f"✅ Background library sync completed: {result}")
            
            return {
                'success': success,
                'message': 'Library sync completed successfully' if success else 'Library sync completed with errors',
                'stats': result,
                'execution_id': execution_id
            }
            
        except Exception as e:
            print(f"❌ Error in background library sync: {e}")
            
            # Update job execution record with error
            self._update_job_execution(execution_id, success=False, error_message=str(e))
            
            return {
                'success': False,
                'message': f'Library sync failed: {str(e)}',
                'error': str(e),
                'execution_id': execution_id
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
                print("🔄 Closing event loop...")
                loop.close()
                
        except Exception as e:
            print(f"❌ Error in sync thread: {e}")
            import traceback
            traceback.print_exc()
            return {'error': str(e)}
    
    async def _run_library_sync_async(self) -> Dict[str, Any]:
        """Run library sync without execution tracking (for scheduled jobs)"""
        try:
            # Mark job as running
            with self._lock:
                self.jobs['library_sync']['running'] = True
                self.jobs['library_sync']['last_run'] = get_utc_now()
            
            # Run the sync in thread pool
            loop = asyncio.get_event_loop()
            
            # Add timeout to prevent hanging
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        self._executor,
                        self._run_library_sync_sync
                    ),
                    timeout=600  # 10 minute timeout
                )
            except asyncio.TimeoutError:
                print("❌ Scheduled library sync timed out after 10 minutes")
                result = {'error': 'Library sync timed out after 10 minutes'}
            
            # Update job status  
            with self._lock:
                self.jobs['library_sync']['stats'] = result
                self.last_library_sync = get_utc_now()
                # Update next run time if auto-scheduling is enabled
                if self.jobs['library_sync'].get('enabled', True) and self.jobs['library_sync'].get('auto_run', True):
                    self.jobs['library_sync']['next_run'] = get_utc_now() + timedelta(seconds=self.jobs['library_sync']['interval_seconds'])
            
            return result
            
        except Exception as e:
            print(f"❌ Error in library sync: {e}")
            return {'error': str(e)}
        finally:
            # Mark job as no longer running
            with self._lock:
                self.jobs['library_sync']['running'] = False
    
    async def _run_download_status_check_async(self) -> Dict[str, Any]:
        """Run download status check without execution tracking (for scheduled jobs)"""
        try:
            # Mark job as running
            with self._lock:
                self.jobs['download_status_check']['running'] = True
                self.jobs['download_status_check']['last_run'] = get_utc_now()
            
            # Run the check in thread pool
            loop = asyncio.get_event_loop()
            
            # Add timeout to prevent hanging
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        self._executor,
                        self._run_download_status_check_sync
                    ),
                    timeout=300  # 5 minute timeout
                )
            except asyncio.TimeoutError:
                print("❌ Scheduled download status check timed out after 5 minutes")
                result = {'error': 'Download status check timed out after 5 minutes'}
            
            # Update job status
            with self._lock:
                self.jobs['download_status_check']['stats'] = result
                self.last_download_check = get_utc_now()
                # Update next run time if auto-scheduling is enabled
                if self.jobs['download_status_check'].get('enabled', True) and self.jobs['download_status_check'].get('auto_run', True):
                    self.jobs['download_status_check']['next_run'] = get_utc_now() + timedelta(seconds=self.jobs['download_status_check']['interval_seconds'])
            
            return result
            
        except Exception as e:
            print(f"❌ Error in download status check: {e}")
            return {'error': str(e)}
        finally:
            # Mark job as no longer running
            with self._lock:
                self.jobs['download_status_check']['running'] = False
    
    async def trigger_download_status_check(self, triggered_by: str = "manual") -> Dict[str, Any]:
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
        
        # Create job execution record
        execution_id = self._create_job_execution('download_status_check', triggered_by)
        
        # Mark job as running
        with self._lock:
            self.jobs['download_status_check']['running'] = True
            self.jobs['download_status_check']['last_run'] = get_utc_now()
        
        try:
            print("🔄 Starting background download status check...")
            
            # Run the download status check in the thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            
            # Add timeout to prevent hanging
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        self._executor,
                        self._run_download_status_check_sync
                    ),
                    timeout=300  # 5 minute timeout
                )
            except asyncio.TimeoutError:
                print("❌ Download status check timed out after 5 minutes")
                result = {'error': 'Download status check timed out after 5 minutes'}
            
            # Determine success based on result
            success = result.get('success', True) if isinstance(result, dict) else not result.get('error')
            
            # Update job execution record
            self._update_job_execution(
                execution_id, 
                success=success, 
                result_data=result if isinstance(result, dict) else {'result': str(result)},
                error_message=result.get('error') if isinstance(result, dict) else None
            )
            
            # Update job status
            with self._lock:
                self.jobs['download_status_check']['stats'] = result
                self.last_download_check = get_utc_now()
                # Update next run time if auto-scheduling is enabled
                if self.jobs['download_status_check'].get('enabled', True) and self.jobs['download_status_check'].get('auto_run', True):
                    self.jobs['download_status_check']['next_run'] = get_utc_now() + timedelta(seconds=self.jobs['download_status_check']['interval_seconds'])
            
            # Trigger HTMX update for any connected clients
            self._trigger_status_update('download_status_check')
            
            print(f"✅ Background download status check completed: {result}")
            
            return {
                'success': success,
                'message': 'Download status check completed successfully' if success else 'Download status check completed with errors',
                'stats': result,
                'execution_id': execution_id
            }
            
        except Exception as e:
            print(f"❌ Error in background download status check: {e}")
            
            # Update job execution record with error
            self._update_job_execution(execution_id, success=False, error_message=str(e))
            
            return {
                'success': False,
                'message': f'Download status check failed: {str(e)}',
                'error': str(e),
                'execution_id': execution_id
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

    def _initialize_jobs(self):
        """Initialize job definitions with default settings"""  
        self.jobs = {
            'library_sync': {
                'name': 'Library Sync',
                'description': 'Syncs Plex library to local database',
                'last_run': None,
                'next_run': None,
                'running': False,
                'interval_seconds': self.library_sync_interval,
                'stats': {},
                'enabled': False,  # Will be overridden by persisted settings
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
                'enabled': False,  # Will be overridden by persisted settings
                'auto_run': False
            },
            'request_submission': {
                'name': 'Request Submission',
                'description': 'Submits approved requests to Radarr/Sonarr services',
                'last_run': None,
                'next_run': None,
                'running': False,
                'interval_seconds': 300,  # 5 minutes
                'stats': {},
                'enabled': False,  # Will be overridden by persisted settings
                'auto_run': False
            }
        }

    def _load_job_settings(self):
        """Load job settings from database"""
        try:
            from sqlmodel import Session
            from ..core.database import engine
            from ..services.settings_service import SettingsService
            
            with Session(engine) as session:
                # Get settings object
                settings = SettingsService.get_settings(session)
                job_settings = settings.get_background_job_settings()
                
                if job_settings:
                    print(f"📥 Loading persisted job settings: {job_settings}")
                    
                    # Apply loaded settings to jobs after initialization
                    if hasattr(self, 'jobs'):
                        for job_name, settings_data in job_settings.items():
                            if job_name in self.jobs:
                                self.jobs[job_name].update({
                                    'enabled': settings_data.get('enabled', False),
                                    'auto_run': settings_data.get('enabled', False),
                                    'interval_seconds': settings_data.get('interval_seconds', self.jobs[job_name]['interval_seconds'])
                                })
                                print(f"📥 Applied settings for {job_name}: enabled={settings_data.get('enabled', False)}, interval={settings_data.get('interval_seconds', 0)}s")
                else:
                    print("📥 No persisted job settings found - using defaults")
                    
        except Exception as e:
            print(f"⚠️ Error loading job settings: {e}")
            print("📥 Using default job settings")
    
    def _create_job_execution(self, job_name: str, triggered_by: str = "scheduler") -> int:
        """Create a new job execution record and return its ID"""
        try:
            from sqlmodel import Session
            from ..core.database import engine
            
            with Session(engine) as session:
                execution = JobExecution(
                    job_name=job_name,
                    started_at=get_utc_now(),
                    status="running",
                    triggered_by=triggered_by
                )
                session.add(execution)
                session.commit()
                session.refresh(execution)
                print(f"📝 Created job execution record #{execution.id} for {job_name}")
                return execution.id
        except Exception as e:
            print(f"⚠️ Error creating job execution record: {e}")
            return None
    
    def _create_completed_job_execution(self, job_name: str, triggered_by: str, started_at: datetime, completed_at: datetime, success: bool, result_data: dict = None, error_message: str = None):
        """Create a completed job execution record directly"""
        try:
            from sqlmodel import Session
            from ..core.database import engine
            
            with Session(engine) as session:
                execution = JobExecution(
                    job_name=job_name,
                    started_at=started_at,
                    completed_at=completed_at,
                    status="success" if success else "failed",
                    result_data=result_data,
                    error_message=error_message,
                    triggered_by=triggered_by,
                    duration_seconds=(completed_at - started_at).total_seconds()
                )
                session.add(execution)
                session.commit()
                session.refresh(execution)
                
                status_icon = "✅" if success else "❌"
                duration = f" ({execution.duration_seconds:.1f}s)" if execution.duration_seconds else ""
                print(f"{status_icon} Created completed job execution record #{execution.id} for {job_name}: {execution.status}{duration}")
                return execution.id
        except Exception as e:
            print(f"⚠️ Error creating completed job execution record: {e}")
            return None
    
    def _update_job_execution(self, execution_id: int, success: bool = True, result_data: Dict[str, Any] = None, error_message: str = None):
        """Update job execution record with completion status"""
        if not execution_id:
            return
            
        try:
            from sqlmodel import Session
            from ..core.database import engine
            
            with Session(engine) as session:
                execution = session.get(JobExecution, execution_id)
                if execution:
                    execution.mark_completed(success=success, result_data=result_data, error_message=error_message)
                    session.add(execution)
                    session.commit()
                    
                    status_icon = "✅" if success else "❌"
                    duration = f" ({execution.duration_seconds:.1f}s)" if execution.duration_seconds else ""
                    print(f"{status_icon} Updated job execution record #{execution_id}: {execution.status}{duration}")
        except Exception as e:
            print(f"⚠️ Error updating job execution record: {e}")
    
    def get_job_execution_history(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """Get paginated job execution history (only completed/failed jobs)"""
        try:
            from sqlmodel import Session, select, func
            from ..core.database import engine
            
            with Session(engine) as session:
                # Get total count
                count_statement = (
                    select(func.count(JobExecution.id))
                    .where(JobExecution.status.in_(["success", "failed"]))
                )
                total_count = session.exec(count_statement).first()
                
                # Get paginated results
                statement = (
                    select(JobExecution)
                    .where(JobExecution.status.in_(["success", "failed"]))
                    .order_by(JobExecution.started_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
                executions = session.exec(statement).all()
                
                history = []
                for execution in executions:
                    history.append({
                        "id": execution.id,
                        "job_name": execution.job_name,
                        "started_at": format_datetime_local(execution.started_at),
                        "completed_at": format_datetime_local(execution.completed_at),
                        "status": execution.status,
                        "result_data": execution.result_data or {},
                        "error_message": execution.error_message,
                        "triggered_by": execution.triggered_by,
                        "duration_seconds": execution.duration_seconds
                    })
                
                return {
                    "history": history,
                    "total_count": total_count or 0,
                    "limit": limit,
                    "offset": offset,
                    "has_more": (offset + len(history)) < (total_count or 0)
                }
        except Exception as e:
            print(f"⚠️ Error getting job execution history: {e}")
            return {
                "history": [],
                "total_count": 0,
                "limit": limit,
                "offset": offset,
                "has_more": False
            }
    
    def clear_job_execution_history(self, keep_recent_days: int = 7) -> Dict[str, Any]:
        """Clear job execution history older than specified days"""
        try:
            from sqlmodel import Session, select, func
            from ..core.database import engine
            
            cutoff_date = get_utc_now() - timedelta(days=keep_recent_days)
            
            with Session(engine) as session:
                # Count records to be deleted
                count_statement = (
                    select(func.count(JobExecution.id))
                    .where(JobExecution.started_at < cutoff_date)
                )
                delete_count = session.exec(count_statement).first() or 0
                
                # Delete old records
                delete_statement = (
                    select(JobExecution)
                    .where(JobExecution.started_at < cutoff_date)
                )
                old_executions = session.exec(delete_statement).all()
                
                for execution in old_executions:
                    session.delete(execution)
                
                session.commit()
                
                print(f"🗑️ Cleared {delete_count} job execution records older than {keep_recent_days} days")
                
                return {
                    "success": True,
                    "deleted_count": delete_count,
                    "cutoff_date": format_datetime_local(cutoff_date)
                }
        except Exception as e:
            print(f"⚠️ Error clearing job execution history: {e}")
            return {
                "success": False,
                "error": str(e),
                "deleted_count": 0
            }

    def _save_job_settings(self):
        """Save current job settings to database"""
        try:
            from sqlmodel import Session
            from ..core.database import engine
            from ..services.settings_service import SettingsService
            
            # Build settings dictionary
            settings_to_save = {}
            for job_name, job in self.jobs.items():
                settings_to_save[job_name] = {
                    'enabled': job.get('enabled', False),
                    'interval_seconds': job.get('interval_seconds', 0)
                }
            
            with Session(engine) as session:
                # Get settings object and update background job settings
                settings = SettingsService.get_settings(session)
                settings.set_background_job_settings(settings_to_save)
                settings.updated_at = get_utc_now()
                session.add(settings)
                session.commit()
                print(f"💾 Saved job settings to database: {settings_to_save}")
                
        except Exception as e:
            print(f"❌ Error saving job settings: {e}")
    
    async def trigger_request_submission(self) -> Dict[str, Any]:
        """Manually trigger request submission job"""
        return await self._execute_job_with_tracking(
            job_name='request_submission',
            job_function=self._run_request_submission_sync,
            triggered_by='manual'
        )
    
    def _run_request_submission_sync(self) -> Dict[str, Any]:
        """
        Synchronous wrapper for the async request submission.
        This runs in a thread pool.
        """
        try:
            print("🔄 Creating new event loop for background request submission...")
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                print("🔄 Starting request submission check...")
                result = loop.run_until_complete(self._process_approved_requests())
                
                print(f"🔄 Request submission completed with result: {result}")
                return result
            finally:
                loop.close()
                
        except Exception as e:
            print(f"❌ Error in _run_request_submission_sync: {e}")
            # Return error result
            return {
                'success': False,
                'error': str(e),
                'processed_count': 0
            }
    
    async def _process_approved_requests(self) -> Dict[str, Any]:
        """Process approved requests and submit them to appropriate services"""
        print("🎬 Starting approved request submission job...")
        
        try:
            from sqlmodel import Session, select
            from ..core.database import engine
            from ..models.media_request import MediaRequest, RequestStatus
            from ..services.multi_instance_integration_service import MultiInstanceIntegrationService
            
            submitted_count = 0
            errors = []
            
            with Session(engine) as session:
                # Get all approved requests that haven't been submitted to services yet
                statement = (
                    select(MediaRequest)
                    .where(MediaRequest.status == RequestStatus.APPROVED)
                    .where(MediaRequest.service_submitted == False)  # Not yet submitted
                )
                
                pending_requests = session.exec(statement).all()
                
                print(f"🎬 Found {len(pending_requests)} approved requests to process")
                
                integration_service = MultiInstanceIntegrationService(session)
                
                for request in pending_requests:
                    try:
                        print(f"🎬 Processing request {request.id}: {request.title} ({request.media_type.value})")
                        
                        # Check if the selected instance is still enabled
                        if request.selected_instance_id:
                            result = await integration_service.submit_to_service(
                                request=request,
                                instance_id=request.selected_instance_id
                            )
                            
                            if result.get('success'):
                                # Mark as submitted
                                request.service_submitted = True
                                request.updated_at = get_utc_now()
                                session.add(request)
                                submitted_count += 1
                                print(f"✅ Successfully submitted request {request.id} to service")
                            else:
                                error_msg = result.get('error', 'Unknown error')
                                errors.append(f"Request {request.id}: {error_msg}")
                                print(f"❌ Failed to submit request {request.id}: {error_msg}")
                        else:
                            error_msg = "No instance selected for request"
                            errors.append(f"Request {request.id}: {error_msg}")
                            print(f"⚠️ Request {request.id} has no selected instance")
                            
                    except Exception as e:
                        error_msg = f"Error processing request {request.id}: {str(e)}"
                        errors.append(error_msg)
                        print(f"❌ {error_msg}")
                
                # Commit all changes
                session.commit()
            
            result = {
                'success': True,
                'submitted_count': submitted_count,
                'total_processed': len(pending_requests),
                'errors': errors
            }
            
            # Update job stats
            with self._lock:
                self.jobs['request_submission']['stats'] = result
                self.jobs['request_submission']['last_run'] = get_utc_now()
                # Update next run time if auto-scheduling is enabled
                if self.jobs['request_submission'].get('enabled', True) and self.jobs['request_submission'].get('auto_run', True):
                    self.jobs['request_submission']['next_run'] = get_utc_now() + timedelta(seconds=self.jobs['request_submission']['interval_seconds'])
            
            print(f"✅ Request submission job completed: {submitted_count} submitted, {len(errors)} errors")
            return result
            
        except Exception as e:
            print(f"❌ Error in request submission job: {e}")
            return {
                'success': False,
                'error': str(e),
                'submitted_count': 0,
                'total_processed': 0,
                'errors': [str(e)]
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


# Auto-start the manager when jobs are enabled
# The scheduler thread only runs jobs that are explicitly enabled
def ensure_scheduler_started():
    """Ensure the scheduler is started when needed"""
    if not background_jobs.running:
        background_jobs.start()
        print("🚀 Background job scheduler started on demand")

# Start the scheduler but jobs remain disabled by default
background_jobs.start()