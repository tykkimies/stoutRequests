#!/usr/bin/env python3
"""
Test Plex friends import
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, '/opt/stoutRequests')

def test_plex_friends():
    try:
        from app.core.database import engine
        from app.services.plex_service import PlexService
        from sqlmodel import Session
        
        with Session(engine) as session:
            plex_service = PlexService(session)
            print("🔍 Testing Plex friends import...")
            print(f"   Plex URL: {plex_service.plex_url}")
            print(f"   Plex Token: {'***' + plex_service.plex_token[-4:] if plex_service.plex_token else 'None'}")
            
            friends = plex_service.get_server_friends()
            print(f"📊 Found {len(friends)} friends")
            
            for friend in friends:
                print(f"   • {friend}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_plex_friends()