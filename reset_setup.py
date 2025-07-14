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
from app.models.role import Role
from app.models.user_permissions import UserPermissions
from app.models.plex_library_item import PlexLibraryItem
from app.models.plex_tv_item import PlexTVItem
from app.models.service_instance import ServiceInstance
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
            
            # Delete all media requests first (references users)
            session.exec(delete(MediaRequest))
            print("   ✅ Cleared media requests")
            
            # Delete user permissions (references users and roles)
            session.exec(delete(UserPermissions))
            print("   ✅ Cleared user permissions")
            
            # Delete Plex library items
            session.exec(delete(PlexLibraryItem))
            print("   ✅ Cleared Plex library items")
            
            # Delete Plex TV items  
            session.exec(delete(PlexTVItem))
            print("   ✅ Cleared Plex TV items")
            
            # Delete service instances
            session.exec(delete(ServiceInstance))
            print("   ✅ Cleared service instances")
            
            # Delete settings before users (due to foreign key constraint)
            session.exec(delete(Settings))
            print("   ✅ Cleared settings")
            
            # Delete all users (before roles due to potential foreign keys)
            session.exec(delete(User))
            print("   ✅ Cleared users")
            
            # Delete all roles last
            session.exec(delete(Role))
            print("   ✅ Cleared roles")
            
            # Commit the changes
            session.commit()
            print("💾 Changes committed to database")
            
            # Recreate default roles
            print("🔐 Creating default roles...")
            from app.services.permissions_service import PermissionsService
            PermissionsService.ensure_default_roles(session)
            print("   ✅ Default roles created (Administrator, Power User, Basic User, Limited User)")
            
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
        print("")
        print("🔐 Note: This reset includes the new role-based permissions system:")
        print("   • The first user to authenticate becomes server owner (unchangeable admin)")
        print("   • Server owner gets 'Administrator' role assigned automatically") 
        print("   • Additional users can be assigned roles via Admin > Users > Permissions")
        print("   • Server owner cannot be demoted, deactivated, or deleted")
        print("   • Default roles: Administrator, Power User, Basic User, Limited User")
        
    except Exception as e:
        print(f"❌ Error resetting configuration: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    reset_configuration()