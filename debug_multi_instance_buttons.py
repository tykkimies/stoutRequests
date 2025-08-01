#!/usr/bin/env python3
"""
Debug script to check multi-instance button functionality

This script will:
1. Check if admin users are getting multiple instances
2. Verify that templates are receiving available_instances data
3. Test the button rendering logic
"""

import asyncio
import sys
sys.path.append('/opt/stoutRequests')

from app.core.database import get_session
from app.models import User
from app.models.service_instance import ServiceInstance, ServiceType
from app.models.media_request import MediaType
from app.services.instance_selection_service import get_instance_selection_service, get_user_available_instances
from sqlmodel import Session, select

async def debug_multi_instance_buttons():
    """Debug multi-instance button functionality"""
    
    session = next(get_session())
    
    print("🔍 DEBUGGING MULTI-INSTANCE BUTTONS")
    print("=" * 50)
    
    # 1. Check available service instances
    print("\n📋 Checking available service instances:")
    instances = session.exec(select(ServiceInstance).where(ServiceInstance.is_enabled == True)).all()
    for instance in instances:
        print(f"  - {instance.name} ({instance.service_type}) - Default Movie: {instance.is_default_movie}, Default TV: {instance.is_default_tv}")
    
    # 2. Check admin users
    print("\n👤 Checking admin users:")
    admin_users = session.exec(select(User).where(User.is_admin == True)).all()
    for user in admin_users:
        print(f"  - {user.username} (ID: {user.id}) - Admin: {user.is_admin}")
        
        # Test instance access for this admin user
        print(f"    Testing instance access for {user.username}:")
        
        # Test movie instances
        movie_instances = await get_user_available_instances(user.id, MediaType.MOVIE, "standard")
        print(f"      Movie instances: {len(movie_instances)} available")
        for instance in movie_instances:
            print(f"        - {instance.name}")
        
        # Test TV instances
        tv_instances = await get_user_available_instances(user.id, MediaType.TV, "standard")
        print(f"      TV instances: {len(tv_instances)} available")
        for instance in tv_instances:
            print(f"        - {instance.name}")
    
    # 3. Test the instance selection service directly
    print("\n🔧 Testing instance selection service:")
    service = await get_instance_selection_service()
    
    if admin_users:
        admin_user = admin_users[0]
        print(f"  Testing with admin user: {admin_user.username}")
        
        # Test movie instances through service
        available_movie_instances = await service.get_available_instances(admin_user.id, MediaType.MOVIE, "standard")
        print(f"    Movie instances from service: {len(available_movie_instances)}")
        for instance in available_movie_instances:
            print(f"      - {instance.name} (ID: {instance.id})")
        
        # Test TV instances through service
        available_tv_instances = await service.get_available_instances(admin_user.id, MediaType.TV, "standard")
        print(f"    TV instances from service: {len(available_tv_instances)}")
        for instance in available_tv_instances:
            print(f"      - {instance.name} (ID: {instance.id})")
    
    # 4. Check if there are any permission records that might be interfering
    print("\n🔐 Checking user permissions:")
    from app.models.user_permissions import UserPermissions
    permissions = session.exec(select(UserPermissions)).all()
    for perm in permissions:
        user = session.get(User, perm.user_id)
        print(f"  - User: {user.username if user else 'Unknown'} (ID: {perm.user_id})")
        print(f"    Instance permissions: {perm.get_instance_permissions()}")
    
    # 5. Test template context generation
    print("\n🎨 Testing template context generation:")
    if admin_users:
        admin_user = admin_users[0]
        
        # Import the template helper function
        from app.main import get_user_instances_for_template
        
        movie_instances_template = await get_user_instances_for_template(admin_user, "movie")
        print(f"  Movie instances for template: {len(movie_instances_template)}")
        for instance in movie_instances_template:
            print(f"    - {instance.name}")
        
        tv_instances_template = await get_user_instances_for_template(admin_user, "tv")
        print(f"  TV instances for template: {len(tv_instances_template)}")
        for instance in tv_instances_template:
            print(f"    - {instance.name}")
        
        mixed_instances_template = await get_user_instances_for_template(admin_user, "mixed")
        print(f"  Mixed instances for template: {len(mixed_instances_template)}")
        for instance in mixed_instances_template:
            print(f"    - {instance.name}")
    
    print("\n" + "=" * 50)
    print("🔍 Debug complete!")

if __name__ == "__main__":
    asyncio.run(debug_multi_instance_buttons())
