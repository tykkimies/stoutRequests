#!/usr/bin/env python3
"""
Fix server owner permissions - ensure full access
"""
import asyncio
import sys
sys.path.append('/opt/stoutRequests')

from sqlmodel import Session, select
from app.core.database import get_session
from app.models import User
from app.models.user_permissions import UserPermissions
from app.models.service_instance import ServiceInstance
from datetime import datetime

def fix_server_owner_permissions():
    """Fix server owner permissions to have full access"""
    print("🔧 Fixing Server Owner Permissions")
    print("=" * 50)
    
    # Get database session
    session = next(get_session())
    
    # Find admin users (server owners)
    admin_users = session.exec(select(User).where(User.is_admin == True)).all()
    
    # Get all service instances to create complete permissions
    all_instances = session.exec(select(ServiceInstance)).all()
    
    for user in admin_users:
        print(f"\n👑 Fixing permissions for admin user: {user.username} (ID: {user.id})")
        
        # Get or create user permissions
        user_perms = session.get(UserPermissions, user.id)
        if not user_perms:
            user_perms = UserPermissions(user_id=user.id)
            session.add(user_perms)
            print("  ✅ Created new permissions record")
        
        # Set all basic permissions to True
        user_perms.can_request_movies = True
        user_perms.can_request_tv = True
        user_perms.can_request_4k = True
        user_perms.auto_approve_enabled = True
        user_perms.max_requests = None  # Unlimited
        user_perms.updated_at = datetime.utcnow()
        
        print("  ✅ Set basic permissions: movies=True, tv=True, 4k=True")
        print("  ✅ Set auto-approve: True")
        print("  ✅ Set max requests: Unlimited")
        
        # Create comprehensive instance permissions
        instance_permissions = {}
        
        # Grant access to all instances
        for instance in all_instances:
            instance_permissions[f"instance_{instance.id}"] = True
            print(f"  ✅ Granted access to instance: {instance.name} (ID: {instance.id})")
        
        # Grant access to all categories
        categories = ["4k", "anime", "foreign", "standard"]
        for category in categories:
            instance_permissions[f"category_{category}"] = True
            print(f"  ✅ Granted access to category: {category}")
        
        # Save instance permissions
        user_perms.set_instance_permissions(instance_permissions)
        print(f"  ✅ Set instance permissions: {len(instance_permissions)} permissions")
        
        # Commit changes
        session.commit()
        print(f"  ✅ Committed changes for {user.username}")
    
    print(f"\n🎉 Fixed permissions for {len(admin_users)} admin users")
    print("Admin users now have full access to all features and instances")

if __name__ == "__main__":
    fix_server_owner_permissions()