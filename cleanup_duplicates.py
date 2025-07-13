#!/usr/bin/env python3
"""
Clean up duplicate entries in the plex_library_item table
"""
import sys
import os
import asyncio

# Add the app directory to the path
sys.path.insert(0, '/opt/stoutRequests')

async def cleanup_duplicates():
    try:
        from app.core.database import engine
        from app.services.plex_sync_service import PlexSyncService
        from sqlmodel import Session
        
        with Session(engine) as session:
            sync_service = PlexSyncService(session)
            print("🧹 Starting duplicate cleanup...")
            await sync_service._cleanup_duplicates()
            print("✅ Duplicate cleanup completed!")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(cleanup_duplicates())