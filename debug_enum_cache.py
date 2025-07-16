#!/usr/bin/env python3
"""
Debug the enum cache issue by examining SQLAlchemy's internal state
"""

import os
from sqlmodel import create_engine, Session, select, SQLModel
from app.core.config import settings
from app.models.media_request import MediaRequest, RequestStatus

def debug_enum_cache():
    """Debug what SQLAlchemy thinks the enum values are"""
    print("🔍 Debugging SQLAlchemy enum cache...")
    
    # Create engine with echo to see SQL
    engine = create_engine(settings.database_url, echo=True)
    
    # Check what SQLAlchemy thinks about the enum
    print(f"\n📋 Python RequestStatus enum values:")
    for status in RequestStatus:
        print(f"   {status.name} = '{status.value}'")
    
    # Try to reflect the database schema
    print(f"\n🔍 Reflecting database metadata...")
    try:
        from sqlalchemy import MetaData, inspect
        metadata = MetaData()
        metadata.reflect(bind=engine)
        
        # Check what SQLAlchemy sees for the enum
        inspector = inspect(engine)
        enums = inspector.get_enums()
        print(f"Database enums found: {enums}")
        
        for enum in enums:
            if enum['name'] == 'requeststatus':
                print(f"RequestStatus enum values: {enum['labels']}")
        
    except Exception as e:
        print(f"❌ Reflection failed: {e}")
    
    # Try a simple test
    print(f"\n🧪 Testing simple query...")
    try:
        with Session(engine) as session:
            # Try without any status filtering first
            all_requests = session.exec(select(MediaRequest)).all()
            print(f"✅ Found {len(all_requests)} total requests")
            
            if all_requests:
                first_request = all_requests[0]
                print(f"First request status: '{first_request.status}' (type: {type(first_request.status)})")
                print(f"First request status value: '{first_request.status.value}'")
                
                # Test enum comparison
                print(f"Testing enum comparisons:")
                print(f"   first_request.status == RequestStatus.APPROVED: {first_request.status == RequestStatus.APPROVED}")
                print(f"   first_request.status.value == 'approved': {first_request.status.value == 'approved'}")
    
    except Exception as e:
        print(f"❌ Query test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_enum_cache()