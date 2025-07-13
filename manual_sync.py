#!/usr/bin/env python3
"""
Manual Plex Library Sync Script
Run this to trigger a sync outside of the web interface
"""
import asyncio
import sys
import os

# Add the app directory to the path
sys.path.insert(0, '/opt/stoutRequests')

async def run_sync():
    try:
        from app.services.plex_sync_service import run_plex_sync
        
        print("🚀 Starting manual Plex library sync...")
        result = await run_plex_sync()
        
        if result.get('error'):
            print(f"❌ Sync failed: {result['error']}")
        else:
            print("✅ Sync completed successfully!")
            print(f"📊 Results:")
            for key, value in result.items():
                print(f"   {key}: {value}")
                
    except Exception as e:
        print(f"❌ Error running sync: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_sync())