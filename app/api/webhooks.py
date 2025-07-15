"""
Webhook endpoints for real-time updates from Radarr/Sonarr
"""

from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlmodel import Session, select
from typing import Dict, Any
import json
from datetime import datetime, timedelta
import time
import asyncio
import logging

from ..core.database import get_session, engine
from ..models.media_request import MediaRequest, RequestStatus, MediaType

# Configure logging for webhooks
logger = logging.getLogger(__name__)

# Rate limiting for webhooks to prevent flooding
webhook_calls = {}
RATE_LIMIT_WINDOW = 60  # seconds  
MAX_CALLS_PER_WINDOW = 100  # max webhook calls per minute
WEBHOOK_ENABLED = False  # Webhooks disabled - investigating performance issues

# Background task queue for webhook processing
webhook_queue = asyncio.Queue(maxsize=1000)  # Limit queue size to prevent memory issues

async def process_webhook_background(payload: Dict[str, Any], webhook_type: str):
    """Process webhook in background to avoid blocking main thread"""
    try:
        logger.info(f"🔄 Processing {webhook_type} webhook in background")
        
        # Create a new database session for background processing
        with Session(engine) as session:
            if webhook_type == "radarr":
                updated_count = await process_radarr_webhook(payload, session)
            elif webhook_type == "sonarr":
                updated_count = await process_sonarr_webhook(payload, session)
            else:
                logger.warning(f"Unknown webhook type: {webhook_type}")
                return
                
        logger.info(f"✅ {webhook_type} webhook processed: {updated_count} requests updated")
        
    except Exception as e:
        logger.error(f"❌ Error processing {webhook_type} webhook in background: {e}")

async def queue_webhook_for_processing(payload: Dict[str, Any], webhook_type: str):
    """Queue webhook for background processing"""
    try:
        # Try to add to queue without blocking
        webhook_queue.put_nowait({"payload": payload, "type": webhook_type})
        logger.info(f"📥 Queued {webhook_type} webhook for background processing")
    except asyncio.QueueFull:
        logger.warning(f"⚠️ Webhook queue full, dropping {webhook_type} webhook")

async def webhook_worker():
    """Background worker to process webhook queue"""
    while True:
        try:
            # Wait for webhook to process
            item = await webhook_queue.get()
            await process_webhook_background(item["payload"], item["type"])
            webhook_queue.task_done()
        except Exception as e:
            logger.error(f"❌ Error in webhook worker: {e}")
            await asyncio.sleep(1)

# Webhook worker will be started by the application startup
_webhook_worker_task = None

async def start_webhook_worker():
    """Start the webhook worker task"""
    global _webhook_worker_task
    if _webhook_worker_task is None:
        _webhook_worker_task = asyncio.create_task(webhook_worker())
        logger.info("🚀 Webhook worker started")

async def stop_webhook_worker():
    """Stop the webhook worker task"""
    global _webhook_worker_task
    if _webhook_worker_task:
        _webhook_worker_task.cancel()
        try:
            await _webhook_worker_task
        except asyncio.CancelledError:
            pass
        _webhook_worker_task = None
        logger.info("🛑 Webhook worker stopped")

def check_rate_limit(endpoint: str) -> bool:
    """Check if endpoint is being rate limited"""
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    
    # Clean old entries
    if endpoint in webhook_calls:
        webhook_calls[endpoint] = [call_time for call_time in webhook_calls[endpoint] if call_time > window_start]
    else:
        webhook_calls[endpoint] = []
    
    # Check if we're over the limit
    if len(webhook_calls[endpoint]) >= MAX_CALLS_PER_WINDOW:
        return False
    
    # Record this call
    webhook_calls[endpoint].append(now)
    return True

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/radarr")
async def radarr_webhook(request: Request):
    """Handle Radarr webhooks - minimal processing to prevent performance issues"""
    try:
        payload = await request.json()
        event_type = payload.get('eventType', 'unknown')
        
        # Just log and return immediately - no processing
        logger.info(f"🎬 RADARR WEBHOOK: {event_type} event received and ignored (webhooks disabled)")
        
        # Always return success to Radarr
        return JSONResponse({
            "success": True,
            "message": f"Radarr webhook received but processing disabled",
            "eventType": event_type
        })
        
    except Exception as e:
        logger.error(f"❌ Error in Radarr webhook: {e}")
        # Still return success to prevent Radarr from retrying
        return JSONResponse({
            "success": True,
            "message": "Webhook received but processing disabled"
        })


@router.post("/sonarr")
async def sonarr_webhook(request: Request):
    """Handle Sonarr webhooks - minimal processing to prevent performance issues"""
    try:
        payload = await request.json()
        event_type = payload.get('eventType', 'unknown')
        
        # Just log and return immediately - no processing
        logger.info(f"📺 SONARR WEBHOOK: {event_type} event received and ignored (webhooks disabled)")
        
        # Always return success to Sonarr
        return JSONResponse({
            "success": True,
            "message": f"Sonarr webhook received but processing disabled",
            "eventType": event_type
        })
        
    except Exception as e:
        logger.error(f"❌ Error in Sonarr webhook: {e}")
        # Still return success to prevent Sonarr from retrying
        return JSONResponse({
            "success": True,
            "message": "Webhook received but processing disabled"
        })


async def process_radarr_webhook(payload: Dict[str, Any], session: Session) -> int:
    """Process Radarr webhook payload and update request status"""
    event_type = payload.get("eventType")
    movie_data = payload.get("movie", {})
    tmdb_id = movie_data.get("tmdbId")
    radarr_id = movie_data.get("id")
    
    if not tmdb_id:
        logger.warning(f"⚠️ Radarr webhook missing TMDB ID: {payload}")
        return 0
    
    # Find matching request - include both requests with radarr_id and approved requests without it
    statement = select(MediaRequest).where(
        MediaRequest.tmdb_id == tmdb_id,
        MediaRequest.media_type == MediaType.MOVIE,
        MediaRequest.status.in_([RequestStatus.APPROVED, RequestStatus.DOWNLOADING])
    )
    requests = session.exec(statement).all()
    
    if not requests:
        logger.info(f"📭 No matching movie requests found for TMDB ID {tmdb_id}")
        return 0
    
    updated_count = 0
    for request in requests:
        old_status = request.status
        new_status = determine_status_from_radarr_event(event_type, payload, old_status)
        
        if new_status != old_status:
            request.status = new_status
            request.updated_at = datetime.utcnow()
            
            # Update Radarr ID if we didn't have it
            if not request.radarr_id and radarr_id:
                request.radarr_id = radarr_id
            
            session.add(request)
            updated_count += 1
            
            logger.info(f"🎬 Updated movie '{request.title}': {old_status.value} → {new_status.value}")
    
    if updated_count > 0:
        try:
            session.commit()
        except Exception as e:
            logger.error(f"❌ Error committing Radarr webhook updates: {e}")
            session.rollback()
            return 0
    
    return updated_count


async def process_sonarr_webhook(payload: Dict[str, Any], session: Session) -> int:
    """Process Sonarr webhook payload and update request status"""
    event_type = payload.get("eventType")
    series_data = payload.get("series", {})
    tmdb_id = series_data.get("tmdbId")
    sonarr_id = series_data.get("id")
    
    if not tmdb_id:
        logger.warning(f"⚠️ Sonarr webhook missing TMDB ID: {payload}")
        return 0
    
    # Find matching request - include both requests with sonarr_id and approved requests without it
    statement = select(MediaRequest).where(
        MediaRequest.tmdb_id == tmdb_id,
        MediaRequest.media_type == MediaType.TV,
        MediaRequest.status.in_([RequestStatus.APPROVED, RequestStatus.DOWNLOADING])
    )
    requests = session.exec(statement).all()
    
    if not requests:
        logger.info(f"📭 No matching TV requests found for TMDB ID {tmdb_id}")
        return 0
    
    updated_count = 0
    for request in requests:
        old_status = request.status
        new_status = determine_status_from_sonarr_event(event_type, payload, old_status)
        
        if new_status != old_status:
            request.status = new_status
            request.updated_at = datetime.utcnow()
            
            # Update Sonarr ID if we didn't have it
            if not request.sonarr_id and sonarr_id:
                request.sonarr_id = sonarr_id
            
            session.add(request)
            updated_count += 1
            
            logger.info(f"📺 Updated TV show '{request.title}': {old_status.value} → {new_status.value}")
    
    if updated_count > 0:
        try:
            session.commit()
        except Exception as e:
            logger.error(f"❌ Error committing Sonarr webhook updates: {e}")
            session.rollback()
            return 0
    
    return updated_count


def determine_status_from_radarr_event(event_type: str, payload: Dict[str, Any], current_status: RequestStatus) -> RequestStatus:
    """Determine new request status based on Radarr webhook event"""
    
    if event_type == "Grab":
        # Download started
        return RequestStatus.DOWNLOADING
    
    elif event_type == "Download":
        # Download completed (legacy, may not be used)
        return RequestStatus.DOWNLOADED
    
    elif event_type == "Import":
        # File imported/downloaded to library (this is the correct Radarr event)
        return RequestStatus.DOWNLOADED
    
    elif event_type == "MovieAdded":
        # Movie added to Radarr (should already be APPROVED)
        return current_status if current_status != RequestStatus.PENDING else RequestStatus.APPROVED
    
    elif event_type == "Rename":
        # File renamed - keep current status
        return current_status
    
    elif event_type == "MovieDelete":
        # Movie deleted from Radarr - back to approved
        return RequestStatus.APPROVED
    
    else:
        logger.warning(f"⚠️ Unknown Radarr event type: {event_type}")
        return current_status


def determine_status_from_sonarr_event(event_type: str, payload: Dict[str, Any], current_status: RequestStatus) -> RequestStatus:
    """Determine new request status based on Sonarr webhook event"""
    
    if event_type == "Grab":
        # Download started
        return RequestStatus.DOWNLOADING
    
    elif event_type == "Download":
        # Episode downloaded - for series requests, any episode = downloaded
        return RequestStatus.DOWNLOADED
    
    elif event_type == "SeriesAdd":
        # Series added to Sonarr (should already be APPROVED)
        return current_status if current_status != RequestStatus.PENDING else RequestStatus.APPROVED
    
    elif event_type == "Rename":
        # File renamed - keep current status
        return current_status
    
    elif event_type == "SeriesDelete":
        # Series deleted from Sonarr - back to approved
        return RequestStatus.APPROVED
    
    else:
        logger.warning(f"⚠️ Unknown Sonarr event type: {event_type}")
        return current_status


@router.get("/test")
async def test_webhooks():
    """Test endpoint to verify webhooks are working"""
    return {
        "message": "Webhooks are working!",
        "webhook_enabled": WEBHOOK_ENABLED,
        "rate_limit": f"{MAX_CALLS_PER_WINDOW} calls per {RATE_LIMIT_WINDOW} seconds",
        "endpoints": {
            "radarr": "/webhooks/radarr",
            "sonarr": "/webhooks/sonarr"
        }
    }


@router.post("/enable")
async def enable_webhooks():
    """Enable webhook processing (admin only)"""
    global WEBHOOK_ENABLED
    WEBHOOK_ENABLED = True
    logger.info("✅ WEBHOOKS ENABLED by admin")
    return {
        "success": True,
        "message": "Webhooks enabled",
        "webhook_enabled": WEBHOOK_ENABLED
    }


@router.post("/disable")
async def disable_webhooks():
    """Disable webhook processing for safety"""
    global WEBHOOK_ENABLED
    WEBHOOK_ENABLED = False
    logger.warning("🚨 WEBHOOKS DISABLED for safety")
    return {
        "success": True,
        "message": "Webhooks disabled for safety",
        "webhook_enabled": WEBHOOK_ENABLED
    }


@router.get("/status")
async def webhook_status(
    request: Request,
    session: Session = Depends(get_session)
):
    """Get webhook status and recent activity for web UI"""
    from datetime import datetime, timedelta
    
    # Get recent requests that could be updated by webhooks
    recent_cutoff = datetime.utcnow() - timedelta(days=7)
    
    # Movie requests 
    movie_stmt = select(MediaRequest).where(
        MediaRequest.media_type == MediaType.MOVIE,
        MediaRequest.status.in_([RequestStatus.APPROVED, RequestStatus.DOWNLOADING]),
        MediaRequest.created_at >= recent_cutoff
    ).order_by(MediaRequest.updated_at.desc())
    
    movie_requests = session.exec(movie_stmt).all()
    
    # TV requests
    tv_stmt = select(MediaRequest).where(
        MediaRequest.media_type == MediaType.TV,
        MediaRequest.status.in_([RequestStatus.APPROVED, RequestStatus.DOWNLOADING]),
        MediaRequest.created_at >= recent_cutoff
    ).order_by(MediaRequest.updated_at.desc())
    
    tv_requests = session.exec(tv_stmt).all()
    
    # Format for display
    def format_request(req):
        status_str = req.status.value if hasattr(req.status, 'value') else str(req.status)
        return {
            "id": req.id,
            "tmdb_id": req.tmdb_id,
            "title": req.title,
            "status": status_str,
            "radarr_id": req.radarr_id,
            "sonarr_id": req.sonarr_id,
            "created_at": req.created_at.isoformat() if req.created_at else None,
            "updated_at": req.updated_at.isoformat() if req.updated_at else None
        }
    
    return {
        "webhook_status": "active",
        "endpoints": {
            "radarr": "/webhooks/radarr (POST only)",
            "sonarr": "/webhooks/sonarr (POST only)",
            "status": "/webhooks/status (GET - this page)"
        },
        "recent_activity": {
            "movies": [format_request(req) for req in movie_requests[:10]],
            "tv_shows": [format_request(req) for req in tv_requests[:10]]
        },
        "statistics": {
            "total_movie_requests": len(movie_requests),
            "total_tv_requests": len(tv_requests),
            "downloading_movies": len([r for r in movie_requests if r.status == RequestStatus.DOWNLOADING]),
            "downloading_tv": len([r for r in tv_requests if r.status == RequestStatus.DOWNLOADING])
        },
        "instructions": {
            "radarr_webhook_url": "http://192.168.1.7:8001/webhooks/radarr",
            "sonarr_webhook_url": "http://192.168.1.7:8001/webhooks/sonarr",
            "setup_guide": "Configure these URLs in Radarr/Sonarr Settings → Connect → Webhook"
        }
    }


@router.get("/dashboard")
async def webhook_dashboard(
    request: Request,
    session: Session = Depends(get_session)
):
    """HTML dashboard for webhook status"""
    from fastapi.responses import HTMLResponse
    from datetime import datetime, timedelta
    
    # Get recent requests data (same as status endpoint)
    recent_cutoff = datetime.utcnow() - timedelta(days=7)
    
    movie_stmt = select(MediaRequest).where(
        MediaRequest.media_type == MediaType.MOVIE,
        MediaRequest.status.in_([RequestStatus.APPROVED, RequestStatus.DOWNLOADING]),
        MediaRequest.created_at >= recent_cutoff
    ).order_by(MediaRequest.updated_at.desc())
    
    movie_requests = session.exec(movie_stmt).all()
    
    tv_stmt = select(MediaRequest).where(
        MediaRequest.media_type == MediaType.TV,
        MediaRequest.status.in_([RequestStatus.APPROVED, RequestStatus.DOWNLOADING]),
        MediaRequest.created_at >= recent_cutoff
    ).order_by(MediaRequest.updated_at.desc())
    
    tv_requests = session.exec(tv_stmt).all()
    
    downloading_movies = [r for r in movie_requests if r.status == RequestStatus.DOWNLOADING]
    downloading_tv = [r for r in tv_requests if r.status == RequestStatus.DOWNLOADING]
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Webhook Status - Stout Requests</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f7; }}
            .container {{ max-width: 1000px; margin: 0 auto; }}
            .header {{ background: white; padding: 20px; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
            .status-card {{ background: white; padding: 20px; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
            .status-good {{ border-left: 4px solid #34c759; }}
            .status-warning {{ border-left: 4px solid #ff9500; }}
            .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
            .request-item {{ padding: 12px; background: #f8f9fa; border-radius: 8px; margin-bottom: 8px; }}
            .request-downloading {{ background: #e3f2fd; border-left: 3px solid #2196f3; }}
            .request-approved {{ background: #f3e5f5; border-left: 3px solid #9c27b0; }}
            .stats {{ display: flex; gap: 20px; }}
            .stat {{ text-align: center; padding: 15px; background: #f8f9fa; border-radius: 8px; flex: 1; }}
            .webhook-url {{ background: #f1f3f4; padding: 10px; border-radius: 6px; font-family: monospace; font-size: 14px; margin: 10px 0; word-break: break-all; }}
            h1 {{ margin: 0; color: #1d1d1f; }}
            h2 {{ color: #1d1d1f; margin-top: 0; }}
            .badge {{ padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; }}
            .badge-downloading {{ background: #e3f2fd; color: #1976d2; }}
            .badge-approved {{ background: #f3e5f5; color: #7b1fa2; }}
            .refresh-note {{ color: #666; font-size: 14px; margin-top: 15px; }}
        </style>
        <script>
            setTimeout(() => location.reload(), 30000); // Auto-refresh every 30 seconds
        </script>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔗 Webhook Status Dashboard</h1>
                <p>Real-time monitoring for Radarr and Sonarr webhook integration</p>
            </div>
            
            <div class="status-card status-good">
                <h2>✅ Webhook System Status: Active</h2>
                <div class="stats">
                    <div class="stat">
                        <strong>{len(movie_requests)}</strong><br>
                        <small>Movie Requests</small>
                    </div>
                    <div class="stat">
                        <strong>{len(downloading_movies)}</strong><br>
                        <small>Movies Downloading</small>
                    </div>
                    <div class="stat">
                        <strong>{len(tv_requests)}</strong><br>
                        <small>TV Requests</small>
                    </div>
                    <div class="stat">
                        <strong>{len(downloading_tv)}</strong><br>
                        <small>TV Downloading</small>
                    </div>
                </div>
            </div>
            
            <div class="grid">
                <div class="status-card">
                    <h2>🎬 Recent Movie Activity</h2>
    """
    
    # Add movie requests
    if movie_requests:
        for req in movie_requests[:8]:
            status_str = req.status.value if hasattr(req.status, 'value') else str(req.status)
            css_class = "request-downloading" if status_str == "downloading" else "request-approved"
            badge_class = "badge-downloading" if status_str == "downloading" else "badge-approved"
            
            html += f"""
                    <div class="request-item {css_class}">
                        <strong>{req.title}</strong>
                        <span class="badge {badge_class}">{status_str.upper()}</span>
                        <br><small>TMDB: {req.tmdb_id} | Radarr ID: {req.radarr_id or 'None'}</small>
                    </div>
            """
    else:
        html += '<p>No recent movie requests found.</p>'
    
    html += """
                </div>
                
                <div class="status-card">
                    <h2>📺 Recent TV Activity</h2>
    """
    
    # Add TV requests
    if tv_requests:
        for req in tv_requests[:8]:
            status_str = req.status.value if hasattr(req.status, 'value') else str(req.status)
            css_class = "request-downloading" if status_str == "downloading" else "request-approved"
            badge_class = "badge-downloading" if status_str == "downloading" else "badge-approved"
            
            html += f"""
                    <div class="request-item {css_class}">
                        <strong>{req.title}</strong>
                        <span class="badge {badge_class}">{status_str.upper()}</span>
                        <br><small>TMDB: {req.tmdb_id} | Sonarr ID: {req.sonarr_id or 'None'}</small>
                    </div>
            """
    else:
        html += '<p>No recent TV requests found.</p>'
    
    html += f"""
                </div>
            </div>
            
            <div class="status-card">
                <h2>🔧 Webhook Configuration</h2>
                <p><strong>Radarr Webhook URL:</strong></p>
                <div class="webhook-url">http://192.168.1.7:8001/webhooks/radarr</div>
                
                <p><strong>Sonarr Webhook URL:</strong></p>
                <div class="webhook-url">http://192.168.1.7:8001/webhooks/sonarr</div>
                
                <p><strong>Setup Instructions:</strong></p>
                <ol>
                    <li>In Radarr/Sonarr, go to <strong>Settings → Connect</strong></li>
                    <li>Click <strong>+</strong> and select <strong>Webhook</strong></li>
                    <li>Use the URLs above and enable: On Grab, On Download, On Import</li>
                    <li>Test the connection to verify it works</li>
                </ol>
                
                <p class="refresh-note">🔄 This page auto-refreshes every 30 seconds</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)