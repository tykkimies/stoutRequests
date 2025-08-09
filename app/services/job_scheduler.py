"""
Modern background job scheduler using APScheduler
Based on patterns from Jellyseerr, Ombi, and FastAPI best practices
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)


class JobScheduler:
    """
    Production-ready job scheduler using APScheduler
    - Non-blocking: Runs in separate asyncio tasks
    - Persistent: Jobs survive application restarts
    - Reliable: Proper error handling and recovery
    - Scalable: Can handle multiple job types efficiently
    """
    
    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self._initialized = False
        self._job_stats = {}
        
    async def initialize(self, database_url: str):
        """Initialize the scheduler with database persistence"""
        if self._initialized:
            return
            
        try:
            # Configure job stores - PostgreSQL for persistence
            jobstores = {
                'default': SQLAlchemyJobStore(url=database_url, tablename='cueplex_jobs')
            }
            
            # Configure executors - AsyncIO for non-blocking execution
            executors = {
                'default': AsyncIOExecutor()
            }
            
            # Job defaults
            job_defaults = {
                'coalesce': True,  # Combine multiple pending executions
                'max_instances': 1,  # Prevent job overlap
                'misfire_grace_time': 300  # 5 minutes grace period
            }
            
            # Create scheduler
            self.scheduler = AsyncIOScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults,
                timezone='UTC'
            )
            
            # Add event listeners for job monitoring
            self.scheduler.add_listener(
                self._job_executed_listener,
                EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED
            )
            
            self._initialized = True
            logger.info("✅ Job scheduler initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize job scheduler: {e}")
            raise
    
    def is_running(self):
        """Check if the scheduler is running"""
        return self._initialized and self.scheduler and self.scheduler.running
    
    async def start(self):
        """Start the scheduler"""
        if not self._initialized:
            raise RuntimeError("Scheduler not initialized. Call initialize() first.")
            
        if self.scheduler and not self.scheduler.running:
            self.scheduler.start()
            logger.info("🚀 Job scheduler started")
            
            # Register default jobs
            await self._register_default_jobs()
    
    async def shutdown(self, wait: bool = True):
        """Gracefully shutdown the scheduler"""
        if self.scheduler and self.scheduler.running:
            logger.info("🛑 Shutting down job scheduler...")
            self.scheduler.shutdown(wait=wait)
            logger.info("✅ Job scheduler shut down gracefully")
    
    def _job_executed_listener(self, event):
        """Handle job execution events"""
        job_id = event.job_id
        
        if event.exception:
            logger.error(f"❌ Job {job_id} failed: {event.exception}")
            self._record_scheduled_job_result(job_id, success=False, error=str(event.exception))
        else:
            logger.info(f"✅ Job {job_id} completed successfully")
            self._record_scheduled_job_result(job_id, success=True)
    
    def _record_job_result_sync(self, job_id: str, success: bool, error: str = None):
        """Record job execution results synchronously"""
        try:
            from ..core.database import engine
            from ..models.job_execution import JobExecution
            from sqlmodel import Session, select
            
            with Session(engine) as session:
                # Find the most recent job execution for this job
                stmt = (
                    select(JobExecution)
                    .where(JobExecution.job_name == job_id)
                    .where(JobExecution.status == "running")
                    .order_by(JobExecution.started_at.desc())
                    .limit(1)
                )
                execution = session.exec(stmt).first()
                
                if execution:
                    execution.completed_at = datetime.utcnow()
                    execution.status = "success" if success else "failed"
                    if error:
                        execution.error_message = error
                    if execution.started_at:
                        execution.duration_seconds = (execution.completed_at - execution.started_at).total_seconds()
                    
                    session.add(execution)
                    session.commit()
                    logger.info(f"📝 Updated job execution record for {job_id}: {execution.status}")
                else:
                    logger.warning(f"⚠️ No running job execution found for {job_id}")
                    
        except Exception as e:
            logger.error(f"Failed to record job result for {job_id}: {e}")
    
    def _record_scheduled_job_result(self, job_id: str, success: bool, error: str = None):
        """Record job execution results for scheduled jobs (creates complete record)"""
        try:
            from ..core.database import engine
            from ..models.job_execution import JobExecution
            from sqlmodel import Session
            
            with Session(engine) as session:
                # Create a complete job execution record for scheduled jobs
                execution = JobExecution(
                    job_name=job_id,
                    started_at=datetime.utcnow(),  # Approximate start time
                    completed_at=datetime.utcnow(),
                    status="success" if success else "failed",
                    triggered_by="scheduler",
                    duration_seconds=0  # We don't have exact timing for scheduled jobs
                )
                
                if error:
                    execution.error_message = error
                
                session.add(execution)
                session.commit()
                logger.info(f"📝 Created job execution record for scheduled job {job_id}: {execution.status}")
                
        except Exception as e:
            logger.error(f"Failed to record scheduled job result for {job_id}: {e}")
    
    def _record_job_result(self, job_id: str, success: bool, error: str = None):
        """Record job execution results (kept for compatibility)"""
        self._record_job_result_sync(job_id, success, error)
    
    async def _async_record_job_result(self, job_id: str, success: bool, error: str = None):
        """Async job result recording"""
        try:
            from ..core.database import engine
            from ..models.job_execution import JobExecution
            from sqlmodel import Session
            
            with Session(engine) as session:
                # Find the most recent job execution for this job
                from sqlmodel import select
                stmt = (
                    select(JobExecution)
                    .where(JobExecution.job_name == job_id)
                    .where(JobExecution.status == "running")
                    .order_by(JobExecution.started_at.desc())
                    .limit(1)
                )
                execution = session.exec(stmt).first()
                
                if execution:
                    execution.completed_at = datetime.utcnow()
                    execution.status = "success" if success else "failed"
                    if error:
                        execution.error_message = error
                    if execution.started_at:
                        execution.duration_seconds = (execution.completed_at - execution.started_at).total_seconds()
                    
                    session.add(execution)
                    session.commit()
                    
        except Exception as e:
            logger.error(f"Failed to record job result: {e}")
    
    async def _register_default_jobs(self):
        """Register the default background jobs"""
        from ..services.settings_service import SettingsService
        from ..core.database import engine
        from sqlmodel import Session
        
        try:
            with Session(engine) as session:
                settings = SettingsService.get_settings(session)
                
                if not settings.is_configured:
                    logger.info("⏳ Skipping job registration - setup not complete")
                    return
                
                # Get job configuration from database
                job_config = settings.get_background_job_settings()
                
                # Default job configurations (all enabled by default with reasonable intervals)
                default_jobs = {
                    "library_sync": {"interval_minutes": 360, "enabled": True},  # 6 hours
                    "download_status_check": {"interval_minutes": 15, "enabled": True},  # 15 minutes
                    "request_submission": {"interval_minutes": 5, "enabled": True},  # 5 minutes  
                    "request_cleanup": {"interval_minutes": 1440, "enabled": True},  # 24 hours
                    "category_cache": {"interval_minutes": 240, "enabled": True}  # 4 hours
                }
                
                # Register jobs with configuration from database or defaults
                for job_id, defaults in default_jobs.items():
                    # Get job-specific config or use defaults
                    job_settings = job_config.get(job_id, defaults)
                    interval_minutes = job_settings.get("interval_minutes", defaults["interval_minutes"])
                    enabled = job_settings.get("enabled", defaults["enabled"])
                    
                    # Job function mapping
                    job_functions = {
                        "library_sync": library_sync_job,
                        "download_status_check": download_status_job,
                        "request_submission": request_submission_job,
                        "request_cleanup": request_cleanup_job,
                        "category_cache": category_cache_job
                    }
                    
                    job_names = {
                        "library_sync": "Library Sync",
                        "download_status_check": "Download Status Check", 
                        "request_submission": "Request Submission",
                        "request_cleanup": "Request Cleanup",
                        "category_cache": "Category Cache Refresh"
                    }
                    
                    await self.schedule_job(
                        job_id=job_id,
                        job_name=job_names[job_id],
                        func=job_functions[job_id],
                        interval_minutes=interval_minutes,
                        enabled=enabled
                    )
                
                logger.info("✅ Default jobs registered successfully")
                
        except Exception as e:
            logger.error(f"❌ Failed to register default jobs: {e}")
    
    async def schedule_job(
        self, 
        job_id: str, 
        job_name: str,
        func,
        interval_minutes: int,
        enabled: bool = True,
        replace_existing: bool = True
    ):
        """Schedule a recurring job"""
        if not self.scheduler:
            raise RuntimeError("Scheduler not initialized")
        
        # Remove existing job if it exists
        if replace_existing and self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        
        if enabled:
            self.scheduler.add_job(
                func=func,
                trigger='interval',
                minutes=interval_minutes,
                id=job_id,
                name=job_name,
                replace_existing=replace_existing
            )
            logger.info(f"📅 Scheduled job '{job_name}' every {interval_minutes} minutes")
        else:
            logger.info(f"⏸️ Job '{job_name}' is disabled")
    
    async def trigger_job(self, job_id: str) -> Dict[str, Any]:
        """Manually trigger a job"""
        if not self.scheduler:
            return {"success": False, "error": "Scheduler not initialized"}
        
        # For library_sync, use the non-blocking queue method
        if job_id == 'library_sync':
            try:
                from ..services.background_jobs import queue_library_sync_immediate
                result = queue_library_sync_immediate()
                return result
            except Exception as e:
                logger.error(f"Failed to queue library sync: {e}")
                return {"success": False, "error": str(e)}
        
        # Job function mapping for other manual triggers
        job_functions = {
            'download_status_check': download_status_job,
            'request_submission': request_submission_job,
            'request_cleanup': request_cleanup_job,
            'category_cache': category_cache_job
        }
        
        try:
            # First try to get the job from scheduler (if it's enabled/scheduled)
            job = self.scheduler.get_job(job_id)
            if job:
                job_func = job.func
            else:
                # If not scheduled, use the function mapping
                job_func = job_functions.get(job_id)
                if not job_func:
                    return {"success": False, "error": f"Job {job_id} not found"}
            
            # Create job execution record
            execution_id = await self._create_job_execution(job_id, "manual")
            
            try:
                # Schedule the job to run immediately in background (non-blocking)
                scheduled_job = self.scheduler.add_job(
                    job_func,
                    'date',  # Run once at a specific time
                    run_date=datetime.now(),  # Run immediately
                    id=f"manual_{job_id}_{execution_id}",  # Unique ID for manual jobs
                    replace_existing=True,
                    misfire_grace_time=300  # 5 minute grace period
                )
                
                return {
                    "success": True,
                    "message": f"Job {job_id} scheduled to run immediately in background",
                    "execution_id": execution_id,
                    "job_scheduled": True
                }
            except Exception as job_error:
                # Update job execution record with failure
                self._record_job_result_sync(job_id, success=False, error=str(job_error))
                raise job_error
            
        except Exception as e:
            logger.error(f"Failed to trigger job {job_id}: {e}")
            return {"success": False, "error": str(e)}
    
    async def _create_job_execution(self, job_name: str, triggered_by: str = "scheduler") -> int:
        """Create a job execution record"""
        try:
            from ..core.database import engine
            from ..models.job_execution import JobExecution
            from sqlmodel import Session
            
            with Session(engine) as session:
                execution = JobExecution(
                    job_name=job_name,
                    started_at=datetime.utcnow(),
                    status="running",
                    triggered_by=triggered_by
                )
                session.add(execution)
                session.commit()
                session.refresh(execution)
                return execution.id
                
        except Exception as e:
            logger.error(f"Failed to create job execution: {e}")
            return None
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get status of a specific job"""
        if not self.scheduler:
            return {"error": "Scheduler not initialized"}
        
        job = self.scheduler.get_job(job_id)
        if not job:
            return {"error": f"Job {job_id} not found"}
        
        return {
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "enabled": True
        }
    
    def list_jobs(self) -> List[Dict[str, Any]]:
        """List all scheduled jobs"""
        if not self.scheduler:
            return []
        
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name, 
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "enabled": True
            })
        
        return jobs
    


# Job function implementations - standalone functions to avoid serialization issues
async def library_sync_job():
    """Library sync job implementation"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        from ..services.plex_sync_service import PlexSyncService
        
        plex_service = PlexSyncService()
        result = await plex_service.sync_library()
        logger.info(f"Library sync completed: {result}")
        
        # After library sync, refresh category cache to update Plex status
        try:
            logger.info("🔄 Refreshing category cache after library sync...")
            cache_result = await category_cache_job()
            logger.info(f"✅ Category cache refreshed: {cache_result}")
        except Exception as cache_error:
            logger.warning(f"⚠️ Failed to refresh category cache after library sync: {cache_error}")
        
        return result
    except Exception as e:
        logger.error(f"Library sync job failed: {e}")
        raise

async def download_status_job():
    """Download status check job implementation"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        from ..services.download_status_service import check_download_status
        
        result = await check_download_status()
        logger.info(f"Download status check completed: {result}")
        return result
    except Exception as e:
        logger.error(f"Download status job failed: {e}")
        raise

async def request_submission_job():
    """Request submission job implementation"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        from ..core.database import engine
        from ..models.media_request import MediaRequest, RequestStatus
        from ..services.multi_instance_integration_service import MultiInstanceIntegrationService
        from sqlmodel import Session, select
        
        with Session(engine) as session:
            # Find approved requests that haven't been submitted to services
            stmt = (
                select(MediaRequest)
                .where(MediaRequest.status == RequestStatus.APPROVED)
                .where(MediaRequest.service_instance_id.is_(None))
            )
            requests = session.exec(stmt).all()
            
            stats = {"submitted_count": 0, "failed_count": 0}
            integration_service = MultiInstanceIntegrationService(session)
            
            for request in requests:
                try:
                    # Use the correct async method
                    result = await integration_service.integrate_request(request)
                    if result:
                        stats["submitted_count"] += 1
                        logger.info(f"Successfully submitted request {request.id}: {request.title}")
                    else:
                        stats["failed_count"] += 1
                        logger.warning(f"Failed to submit request {request.id}: {request.title}")
                except Exception as e:
                    logger.error(f"Failed to submit request {request.id}: {e}")
                    stats["failed_count"] += 1
            
            logger.info(f"Request submission completed: {stats}")
            return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"Request submission job failed: {e}")
        raise

async def request_cleanup_job():
    """Request cleanup job implementation"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        from ..core.database import engine
        from ..models.media_request import MediaRequest, RequestStatus
        from ..services.settings_service import SettingsService
        from sqlmodel import Session, select
        from datetime import datetime, timedelta
        
        with Session(engine) as session:
            settings = SettingsService.get_settings(session)
            retention_days = settings.request_cleanup_retention_days or 30
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
            
            # Find old completed/available requests
            stmt = (
                select(MediaRequest)
                .where(MediaRequest.status.in_([RequestStatus.AVAILABLE, RequestStatus.REJECTED]))
                .where(MediaRequest.updated_at < cutoff_date)
            )
            old_requests = session.exec(stmt).all()
            
            stats = {
                "total_found": len(old_requests),
                "cleaned_count": 0,
                "cutoff_date": cutoff_date.strftime("%Y-%m-%d")
            }
            
            for request in old_requests:
                try:
                    session.delete(request)
                    stats["cleaned_count"] += 1
                except Exception as e:
                    logger.error(f"Failed to delete request {request.id}: {e}")
            
            session.commit()
            logger.info(f"Request cleanup completed: {stats}")
            return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"Request cleanup job failed: {e}")
        raise

async def category_cache_job():
    """
    🚀 OPTIMIZED: Category cache refresh job - uses performance optimizations
    - Uses new database indexes for faster queries
    - Integrates with batch instance loading and request status caching
    - Clears performance caches to ensure fresh data
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        from ..services.tmdb_service import TMDBService
        from ..models.category_cache import CategoryCache
        from ..core.database import engine
        from sqlmodel import Session, select
        from datetime import datetime, timedelta
        
        with Session(engine) as session:
            # 🚀 Clear performance caches before refresh to ensure fresh data
            try:
                from ..services.request_status_service import get_request_status_service
                from ..services.instance_selection_service import _user_instance_cache
                
                # Clear request status cache
                status_service = get_request_status_service(session)
                status_service.invalidate_cache()
                
                # Clear instance permissions cache
                _user_instance_cache.clear()
                
                logger.info("🧹 Cleared performance caches before refresh")
            except Exception as cache_clear_error:
                logger.warning(f"⚠️ Failed to clear performance caches: {cache_clear_error}")
            
            tmdb_service = TMDBService(session)
            
            # Categories to cache for homepage performance
            categories = [
                ("movie", "popular"),
                ("movie", "top_rated"), 
                ("movie", "upcoming"),
                ("movie", "trending"),
                ("tv", "popular"),
                ("tv", "top_rated"),
                ("tv", "on_the_air"),
                ("tv", "trending")
            ]
            
            stats = {"cached_count": 0, "cache_size": 0, "updated": 0, "created": 0, "cache_cleared": True}
            cache_duration_hours = 24  # Cache expires after 24 hours (1 day)
            
            for media_type, category in categories:
                try:
                    # Generate cache key
                    cache_key = CategoryCache.generate_cache_key(media_type, category, page=1)
                    
                    # 🚀 Use optimized query with new indexes
                    stmt = select(CategoryCache).where(CategoryCache.cache_key == cache_key)
                    existing_cache = session.exec(stmt).first()
                    
                    # Fetch fresh data from TMDB
                    data = None
                    if category == "popular":
                        data = tmdb_service.get_popular(media_type, page=1)
                    elif category == "top_rated":
                        data = tmdb_service.get_top_rated(media_type, page=1)
                    elif category == "upcoming" and media_type == "movie":
                        data = tmdb_service.get_upcoming_movies(page=1)
                    elif category == "on_the_air" and media_type == "tv":
                        # For TV "on the air", use discover with air_date filters
                        data = tmdb_service.discover_tv(page=1, sort_by="popularity.desc")
                    elif category == "trending":
                        data = tmdb_service.get_trending(media_type, page=1)
                    
                    if data and "results" in data:
                        expires_at = datetime.utcnow() + timedelta(hours=cache_duration_hours)
                        
                        # 🚀 PERFORMANCE: Pre-process the data with Plex status information
                        # This allows cached data to include status information and eliminates real-time checking
                        try:
                            # Add Plex status to all items in the cache data
                            from ..services.plex_sync_service import PlexSyncService
                            sync_service = PlexSyncService(session)
                            
                            # Extract TMDB IDs for batch status checking
                            tmdb_ids = [item.get('id') for item in data.get('results', [])]
                            
                            if tmdb_ids:
                                # Use fast status checking (skip expensive TV completion for cache)
                                skip_tv_completion = (media_type == 'tv')
                                status_map = sync_service.check_items_status(tmdb_ids, media_type, skip_tv_completion=skip_tv_completion)
                                
                                # Add status and in_plex properties to each item
                                for item in data.get('results', []):
                                    tmdb_id = item.get('id')
                                    status = status_map.get(tmdb_id, 'available')
                                    item['status'] = status
                                    item['in_plex'] = (status == 'in_plex')
                                    item['media_type'] = media_type  # Ensure media_type is set
                                
                                logger.info(f"🚀 Added Plex status to {len(tmdb_ids)} {media_type}/{category} items in cache")
                                
                        except Exception as preprocess_error:
                            logger.warning(f"⚠️ Failed to add Plex status to cache {media_type}/{category}: {preprocess_error}")
                        
                        if existing_cache:
                            # Update existing cache entry
                            existing_cache.set_data(data)
                            existing_cache.cached_at = datetime.utcnow()
                            existing_cache.expires_at = expires_at
                            session.add(existing_cache)
                            stats["updated"] += 1
                            logger.info(f"✅ Updated cache for {media_type}/{category}: {len(data['results'])} items")
                        else:
                            # Create new cache entry
                            cache_entry = CategoryCache(
                                cache_key=cache_key,
                                media_type=media_type,
                                category=category,
                                cached_at=datetime.utcnow(),
                                expires_at=expires_at,
                                page_count=1
                            )
                            cache_entry.set_data(data)
                            session.add(cache_entry)
                            stats["created"] += 1
                            logger.info(f"✅ Created cache for {media_type}/{category}: {len(data['results'])} items")
                        
                        stats["cached_count"] += 1
                        stats["cache_size"] += len(data["results"])
                        
                except Exception as e:
                    logger.error(f"❌ Failed to cache {media_type}/{category}: {e}")
            
            # Commit all cache updates
            session.commit()
            
            # 🚀 OPTIMIZED: Clean up expired cache entries using new indexes
            expired_stmt = select(CategoryCache).where(CategoryCache.expires_at < datetime.utcnow())
            expired_entries = session.exec(expired_stmt).all()
            for expired in expired_entries:
                session.delete(expired)
            
            if expired_entries:
                session.commit()
                logger.info(f"🧹 Cleaned up {len(expired_entries)} expired cache entries")
            
            logger.info(f"🚀 Optimized category cache refresh completed: {stats}")
            return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"❌ Category cache job failed: {e}")
        raise


# Global scheduler instance
job_scheduler = JobScheduler()


@asynccontextmanager
async def lifespan_manager(database_url: str):
    """Lifespan manager for FastAPI integration"""
    try:
        # Initialize and start scheduler
        await job_scheduler.initialize(database_url)
        await job_scheduler.start()
        yield job_scheduler
    finally:
        # Graceful shutdown
        await job_scheduler.shutdown()