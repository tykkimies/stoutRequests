#!/usr/bin/env python3
"""
Force SQLAlchemy to refresh metadata and recognize new enum values
"""

import os
import sys
from sqlmodel import SQLModel, create_engine
from app.core.config import settings

def refresh_metadata():
    """Force refresh of SQLAlchemy metadata"""
    print("🔄 Refreshing SQLAlchemy metadata...")
    
    try:
        # Create a new engine instance
        engine = create_engine(settings.database_url, echo=True)
        
        # Clear any cached metadata
        if hasattr(SQLModel, 'metadata'):
            print("🗑️ Clearing existing metadata...")
            SQLModel.metadata.clear()
        
        # Force reflection of database structure
        print("🔍 Reflecting database structure...")
        SQLModel.metadata.reflect(bind=engine)
        
        # Import the models to register them
        print("📥 Importing models...")
        from app.models.media_request import MediaRequest, RequestStatus
        from app.models.user import User
        from app.models.settings import Settings
        
        print("✅ Metadata refresh completed!")
        
        # Test enum values
        print("🧪 Testing enum values...")
        for status in RequestStatus:
            print(f"   {status.name} = '{status.value}'")
            
        return True
        
    except Exception as e:
        print(f"❌ Metadata refresh failed: {e}")
        return False

if __name__ == "__main__":
    success = refresh_metadata()
    if success:
        print("\n🎉 SQLAlchemy metadata refreshed successfully!")
    else:
        print("\n❌ Metadata refresh failed.")