#!/usr/bin/env python3
"""
Force complete metadata refresh to fix enum cache issues
"""

import os
import sys
import importlib

def force_metadata_refresh():
    """Force complete refresh of all SQLAlchemy metadata"""
    print("🔄 Forcing complete metadata refresh...")
    
    # Clear all cached modules
    modules_to_clear = []
    for module_name in list(sys.modules.keys()):
        if module_name.startswith('app.') or module_name == 'app':
            modules_to_clear.append(module_name)
    
    print(f"🗑️ Clearing {len(modules_to_clear)} cached modules...")
    for module_name in modules_to_clear:
        if module_name in sys.modules:
            del sys.modules[module_name]
    
    # Clear SQLModel metadata
    try:
        from sqlmodel import SQLModel
        if hasattr(SQLModel, 'metadata'):
            SQLModel.metadata.clear()
            print("🗑️ Cleared SQLModel metadata cache")
    except ImportError:
        pass
    
    # Now import fresh
    print("📥 Importing fresh modules...")
    from sqlmodel import create_engine, Session, select
    from app.core.config import settings
    from app.models.media_request import MediaRequest, RequestStatus
    
    # Create completely new engine instance
    engine = create_engine(settings.database_url, echo=False)
    print("🔗 Created fresh database engine")
    
    # Test the connection
    print("🧪 Testing database queries...")
    with Session(engine) as session:
        try:
            # Test basic query
            result = session.exec(select(MediaRequest)).all()
            print(f"✅ Basic query successful: {len(result)} requests found")
            
            # Test enum-based queries
            pending_count = len(session.exec(select(MediaRequest).where(MediaRequest.status == RequestStatus.PENDING)).all())
            approved_count = len(session.exec(select(MediaRequest).where(MediaRequest.status == RequestStatus.APPROVED)).all())
            available_count = len(session.exec(select(MediaRequest).where(MediaRequest.status == RequestStatus.AVAILABLE)).all())
            rejected_count = len(session.exec(select(MediaRequest).where(MediaRequest.status == RequestStatus.REJECTED)).all())
            
            print(f"✅ Status-based queries successful:")
            print(f"   - Pending: {pending_count}")
            print(f"   - Approved: {approved_count}")
            print(f"   - Available: {available_count}")
            print(f"   - Rejected: {rejected_count}")
            
            return True
            
        except Exception as e:
            print(f"❌ Database test failed: {e}")
            return False

if __name__ == "__main__":
    success = force_metadata_refresh()
    if success:
        print("\n🎉 Metadata refresh successful! Application should now work correctly.")
    else:
        print("\n❌ Metadata refresh failed. There may be deeper issues.")