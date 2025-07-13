#!/usr/bin/env python3
"""
Test recent requests functionality
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, '/opt/stoutRequests')

def test_recent_requests():
    try:
        from app.core.database import engine
        from app.models.media_request import MediaRequest
        from sqlmodel import Session, select
        
        with Session(engine) as session:
            # Get recent requests
            recent_statement = select(MediaRequest).order_by(
                MediaRequest.created_at.desc()
            ).limit(5)
            
            recent_requests = session.exec(recent_statement).all()
            print(f"📊 Found {len(recent_requests)} recent requests:")
            
            for request in recent_requests:
                # Test enum access
                media_type_str = request.media_type.value if hasattr(request.media_type, 'value') else str(request.media_type)
                status_str = request.status.value if hasattr(request.status, 'value') else str(request.status)
                
                print(f"   • {request.title} ({media_type_str}) - Status: {status_str}")
                print(f"     TMDB ID: {request.tmdb_id}, Created: {request.created_at}")
                
            if not recent_requests:
                print("   No requests found - this is expected if no requests have been made yet")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_recent_requests()