#!/usr/bin/env python3
"""
Test script to manually check download status
"""
import asyncio
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from sqlmodel import Session
from app.core.database import engine
from app.services.download_status_service import DownloadStatusService

async def test_download_status():
    """Test the download status service"""
    print("🚀 Testing Download Status Service...")
    
    with Session(engine) as session:
        service = DownloadStatusService(session)
        stats = await service.check_download_statuses()
        
        print(f"📊 Results: {stats}")

if __name__ == "__main__":
    asyncio.run(test_download_status())