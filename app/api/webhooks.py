"""
Webhook endpoints for real-time updates from Radarr/Sonarr
"""

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlmodel import Session, select
from typing import Dict, Any
import json
from datetime import datetime

from ..core.database import get_session
from ..models.media_request import MediaRequest, RequestStatus, MediaType

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/radarr")
async def radarr_webhook(
    request: Request,
    session: Session = Depends(get_session)
):
    """Handle Radarr webhooks for real-time download status updates"""
    try:
        payload = await request.json()
        print(f"🎬 RADARR WEBHOOK: Received {payload.get('eventType', 'unknown')} event")
        print(f"   Payload: {json.dumps(payload, indent=2)}")
        
        updated_count = await process_radarr_webhook(payload, session)
        
        return JSONResponse({
            "success": True,
            "message": f"Processed Radarr webhook, updated {updated_count} requests",
            "eventType": payload.get("eventType")
        })
        
    except Exception as e:
        print(f"❌ Error processing Radarr webhook: {e}")
        # Don't fail the webhook - Radarr expects 200
        return JSONResponse({
            "success": False,
            "error": str(e)
        })


@router.post("/sonarr")
async def sonarr_webhook(
    request: Request,
    session: Session = Depends(get_session)
):
    """Handle Sonarr webhooks for real-time download status updates"""
    try:
        payload = await request.json()
        print(f"📺 SONARR WEBHOOK: Received {payload.get('eventType', 'unknown')} event")
        print(f"   Payload: {json.dumps(payload, indent=2)}")
        
        updated_count = await process_sonarr_webhook(payload, session)
        
        return JSONResponse({
            "success": True,
            "message": f"Processed Sonarr webhook, updated {updated_count} requests",
            "eventType": payload.get("eventType")
        })
        
    except Exception as e:
        print(f"❌ Error processing Sonarr webhook: {e}")
        # Don't fail the webhook - Sonarr expects 200
        return JSONResponse({
            "success": False,
            "error": str(e)
        })


async def process_radarr_webhook(payload: Dict[str, Any], session: Session) -> int:
    """Process Radarr webhook payload and update request status"""
    event_type = payload.get("eventType")
    movie_data = payload.get("movie", {})
    tmdb_id = movie_data.get("tmdbId")
    radarr_id = movie_data.get("id")
    
    if not tmdb_id:
        print(f"⚠️ Radarr webhook missing TMDB ID: {payload}")
        return 0
    
    # Find matching request
    statement = select(MediaRequest).where(
        MediaRequest.tmdb_id == tmdb_id,
        MediaRequest.media_type == MediaType.MOVIE,
        MediaRequest.radarr_id.isnot(None)  # Only update requests sent to Radarr
    )
    requests = session.exec(statement).all()
    
    if not requests:
        print(f"📭 No matching movie requests found for TMDB ID {tmdb_id}")
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
            
            print(f"🎬 Updated movie '{request.title}': {old_status.value} → {new_status.value}")
    
    if updated_count > 0:
        session.commit()
    
    return updated_count


async def process_sonarr_webhook(payload: Dict[str, Any], session: Session) -> int:
    """Process Sonarr webhook payload and update request status"""
    event_type = payload.get("eventType")
    series_data = payload.get("series", {})
    tmdb_id = series_data.get("tmdbId")
    sonarr_id = series_data.get("id")
    
    if not tmdb_id:
        print(f"⚠️ Sonarr webhook missing TMDB ID: {payload}")
        return 0
    
    # Find matching request
    statement = select(MediaRequest).where(
        MediaRequest.tmdb_id == tmdb_id,
        MediaRequest.media_type == MediaType.TV,
        MediaRequest.sonarr_id.isnot(None)  # Only update requests sent to Sonarr
    )
    requests = session.exec(statement).all()
    
    if not requests:
        print(f"📭 No matching TV requests found for TMDB ID {tmdb_id}")
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
            
            print(f"📺 Updated TV show '{request.title}': {old_status.value} → {new_status.value}")
    
    if updated_count > 0:
        session.commit()
    
    return updated_count


def determine_status_from_radarr_event(event_type: str, payload: Dict[str, Any], current_status: RequestStatus) -> RequestStatus:
    """Determine new request status based on Radarr webhook event"""
    
    if event_type == "Grab":
        # Download started
        return RequestStatus.DOWNLOADING
    
    elif event_type == "Download":
        # Download completed
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
        print(f"⚠️ Unknown Radarr event type: {event_type}")
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
        print(f"⚠️ Unknown Sonarr event type: {event_type}")
        return current_status


@router.get("/test")
async def test_webhooks():
    """Test endpoint to verify webhooks are working"""
    return {
        "message": "Webhooks are working!",
        "endpoints": {
            "radarr": "/webhooks/radarr",
            "sonarr": "/webhooks/sonarr"
        }
    }