#!/usr/bin/env python3
"""
Fix server owner permissions completely
"""
import sys
sys.path.append('/opt/stoutRequests')

from sqlmodel import Session, select
from app.core.database import get_session
from app.models import User
from app.models.user_permissions import UserPermissions
from app.models.service_instance import ServiceInstance
from datetime import datetime

def fix_server_owner_complete():
    """Fix server owner permissions completely"""
    print("🔧 Fixing Server Owner Permissions (Complete)")
    print("=" * 50)
    
    # Get database session
    session = next(get_session())
    
    # Find the first created user (server owner)
    server_owner = session.exec(select(User).order_by(User.created_at)).first()
    
    if not server_owner:
        print("❌ No users found!")
        return
    
    print(f"👑 Server Owner: {server_owner.username} (ID: {server_owner.id})")
    print(f"   - Current is_admin: {server_owner.is_admin}")
    print(f"   - Current is_server_owner: {server_owner.is_server_owner}")
    
    # Set server owner flags
    server_owner.is_admin = True
    server_owner.is_server_owner = True
    server_owner.updated_at = datetime.utcnow()
    
    print("   ✅ Set is_admin = True")
    print("   ✅ Set is_server_owner = True")
    
    # Get or create user permissions
    user_perms = session.get(UserPermissions, server_owner.id)
    if not user_perms:
        user_perms = UserPermissions(user_id=server_owner.id)
        session.add(user_perms)
        print("   ✅ Created new permissions record")
    
    # Set ALL permissions to True/Unlimited
    user_perms.can_request_movies = True
    user_perms.can_request_tv = True
    user_perms.can_request_4k = True
    user_perms.auto_approve_enabled = True
    user_perms.max_requests = None  # Unlimited
    user_perms.updated_at = datetime.utcnow()
    
    print("   ✅ Set all media permissions: True")
    print("   ✅ Set auto-approve: True")  
    print("   ✅ Set max requests: Unlimited")
    
    # Get all service instances and grant access to everything
    all_instances = session.exec(select(ServiceInstance)).all()
    
    # Create comprehensive instance permissions
    instance_permissions = {}
    
    # Grant access to all instances
    for instance in all_instances:
        instance_permissions[f"instance_{instance.id}"] = True
        print(f"   ✅ Granted access to instance: {instance.name} (ID: {instance.id})")
    
    # Grant access to all possible categories
    all_categories = ["4k", "anime", "foreign", "standard", "hdr", "dolby", "imax"]
    for category in all_categories:
        instance_permissions[f"category_{category}"] = True
        print(f"   ✅ Granted access to category: {category}")
    
    # Save instance permissions
    user_perms.set_instance_permissions(instance_permissions)
    print(f"   ✅ Set instance permissions: {len(instance_permissions)} total permissions")
    
    # Commit all changes
    session.commit()
    print(f"\n🎉 Server Owner {server_owner.username} now has FULL ACCESS to everything!")
    print("   - is_admin: True")
    print("   - is_server_owner: True") 
    print("   - All media types: Enabled")
    print("   - All service instances: Enabled")
    print("   - All categories: Enabled")
    print("   - Auto-approve: Enabled")
    print("   - Request limits: Unlimited")

if __name__ == "__main__":
    fix_server_owner_complete()