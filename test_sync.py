#!/usr/bin/env python3
"""
Test the Plex library sync with improved duplicate handling
"""
import sys
import os
import asyncio

# Add the app directory to the path
sys.path.insert(0, '/opt/stoutRequests')

async def test_sync():
    try:
        from app.core.database import engine
        from app.services.plex_sync_service import PlexSyncService
        from sqlmodel import Session
        
        with Session(engine) as session:
            sync_service = PlexSyncService(session)
            print("🔄 Starting test sync...")
            result = await sync_service.sync_library()
            print(f"📊 Sync result: {result}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_sync())