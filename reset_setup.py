#!/usr/bin/env python3
"""
Reset configuration script for Stout Requests
This will clear all settings and users to allow testing setup from scratch
"""
import sys
import os
sys.path.append('/opt/stoutRequests')

from app.core.database import engine
from app.models.settings import Settings
from app.models.user import User
from app.models.media_request import MediaRequest
from sqlmodel import Session, delete

def reset_configuration():
    """Reset all configuration and user data"""
    print("🔄 Resetting Stout Requests configuration...")
    
    try:
        # Create a session
        with Session(engine) as session:
            print("📊 Connected to database")
            
            # Clear all tables (respecting foreign key constraints)
            print("🗑️  Clearing all data...")
            
            # Delete all media requests first
            session.exec(delete(MediaRequest))
            print("   ✅ Cleared media requests")
            
            # Delete settings before users (due to foreign key constraint)
            session.exec(delete(Settings))
            print("   ✅ Cleared settings")
            
            # Delete all users last
            session.exec(delete(User))
            print("   ✅ Cleared users")
            
            # Commit the changes
            session.commit()
            print("💾 Changes committed to database")
            
        # Clean up temporary files
        import glob
        temp_files = glob.glob("/tmp/stout_setup_*.json")
        for file in temp_files:
            try:
                os.remove(file)
                print(f"   🗑️ Removed {file}")
            except:
                pass
                
        print("\n🎉 Configuration reset complete!")
        print("📝 You can now visit /setup to go through the setup process again")
        print("🌐 The app will redirect to setup automatically when you visit /")
        
    except Exception as e:
        print(f"❌ Error resetting configuration: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    reset_configuration()