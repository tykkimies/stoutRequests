#!/usr/bin/env python3
"""
Test script to verify enum fix is working correctly.
Run this after restarting the application.
"""

import os
import sys

def test_enum_fix():
    """Test that enum values work correctly"""
    print("🧪 Testing enum fix...")
    
    try:
        from sqlmodel import create_engine, Session, select
        from app.core.config import settings
        from app.models.media_request import MediaRequest, RequestStatus
        
        # Test Python enum values
        print("✅ Python enum values:")
        for status in RequestStatus:
            print(f"   {status.name} = '{status.value}'")
        
        # Test database connection
        print("\n🔗 Testing database connection...")
        engine = create_engine(settings.database_url)
        
        with Session(engine) as session:
            # Test simple query
            statement = select(MediaRequest).limit(3)
            results = session.exec(statement).all()
            
            print(f"✅ Database query successful! Found {len(results)} requests:")
            for req in results:
                print(f"   - {req.title}: status = '{req.status.value}'")
        
        # Test status service
        print("\n⚙️ Testing download status service...")
        from app.services.download_status_service import DownloadStatusService
        
        with Session(engine) as session:
            service = DownloadStatusService(session)
            requests_to_check = service._get_approved_requests()
            print(f"✅ Download status service query successful! Found {len(requests_to_check)} requests to check")
        
        print("\n🎉 All tests passed! Enum fix is working correctly.")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        print("\n🔧 Troubleshooting:")
        print("1. Make sure the application has been restarted")
        print("2. Check that the database enum was properly recreated")
        print("3. Verify no import cache issues exist")
        return False

if __name__ == "__main__":
    success = test_enum_fix()
    if success:
        print("\n✅ Ready to use the application!")
    else:
        print("\n❌ Please restart the application and try again.")