#!/usr/bin/env python3

import asyncio
import sys
sys.path.append('/opt/stoutRequests')

from app.core.database import get_session
from app.models.user import User
from app.models.service_instance import ServiceInstance, ServiceType
from app.models.user_permissions import UserPermissions
from app.models.media_request import MediaType
from app.services.instance_selection_service import get_user_available_instances
from app.main import get_instances_for_media_type
from sqlmodel import Session, select

async def debug_movie_instance_issue():
    """Debug why movies show 'no access' while TV works"""
    
    print("🔍 DEBUG: Movie Instance Issue Analysis")
    print("=" * 50)
    
    # Get database session
    session = next(get_session()) 
    
    # 1. Check all service instances
    print("\n📋 1. All Service Instances:")
    instances_stmt = select(ServiceInstance)
    all_instances = session.exec(instances_stmt).all()
    
    radarr_instances = []
    sonarr_instances = []
    
    for instance in all_instances:
        service_type = instance.service_type.value if hasattr(instance.service_type, 'value') else str(instance.service_type)
        print(f"  - {instance.name}: {service_type} (ID: {instance.id}, Enabled: {instance.is_enabled})")
        
        if service_type == 'radarr':
            radarr_instances.append(instance)
        elif service_type == 'sonarr':
            sonarr_instances.append(instance)
    
    print(f"\n📊 Summary: {len(radarr_instances)} Radarr instances, {len(sonarr_instances)} Sonarr instances")
    
    # 2. Check users (find an admin user)
    print("\n👤 2. Finding Admin User:")
    users_stmt = select(User).where(User.is_admin == True)
    admin_users = session.exec(users_stmt).all()
    
    if not admin_users:
        print("❌ No admin users found, checking all users...")
        users_stmt = select(User)
        admin_users = session.exec(users_stmt).all()
    
    if not admin_users:
        print("❌ No users found at all!")
        return
    
    admin_user = admin_users[0]
    print(f"  Using user: {admin_user.username} (ID: {admin_user.id}, Admin: {admin_user.is_admin})")
    
    # 3. Check user permissions
    print("\n🔐 3. User Permissions:")
    perms_stmt = select(UserPermissions).where(UserPermissions.user_id == admin_user.id)
    user_permissions = session.exec(perms_stmt).first()
    
    if user_permissions:
        print(f"  Has permissions: {user_permissions.get_instance_permissions()}")
    else:
        print("  No explicit permissions found")
    
    # 4. Test get_instances_for_media_type function directly
    print("\n🧪 4. Testing get_instances_for_media_type:")
    
    movie_instances = await get_instances_for_media_type(admin_user.id, "movie")
    print(f"  Movie instances: {len(movie_instances)}")
    for instance in movie_instances:
        print(f"    - {instance.name} ({instance.service_type.value})")
    
    tv_instances = await get_instances_for_media_type(admin_user.id, "tv")
    print(f"  TV instances: {len(tv_instances)}")
    for instance in tv_instances:
        print(f"    - {instance.name} ({instance.service_type.value})")
    
    # 5. Test the underlying service directly
    print("\n🔧 5. Testing InstanceSelectionService directly:")
    
    movie_instances_direct = await get_user_available_instances(admin_user.id, MediaType.MOVIE)
    print(f"  Direct movie instances: {len(movie_instances_direct)}")
    for instance in movie_instances_direct:
        print(f"    - {instance.name} ({instance.service_type.value})")
    
    tv_instances_direct = await get_user_available_instances(admin_user.id, MediaType.TV)
    print(f"  Direct TV instances: {len(tv_instances_direct)}")
    for instance in tv_instances_direct:
        print(f"    - {instance.name} ({instance.service_type.value})")
    
    # 6. Check Radarr instance configuration specifically
    print("\n⚙️ 6. Radarr Instance Details:")
    for instance in radarr_instances:
        print(f"  Instance: {instance.name}")
        print(f"    Service Type: {instance.service_type} (raw: {type(instance.service_type)})")
        print(f"    Enabled: {instance.is_enabled}")
        print(f"    Default Movie: {instance.is_default_movie}")
        print(f"    Default TV: {instance.is_default_tv}")
        print(f"    Quality Tier: {instance.quality_tier}")
        print(f"    Category: {instance.instance_category}")
    
    # 7. Check Sonarr instance configuration for comparison
    print("\n⚙️ 7. Sonarr Instance Details (for comparison):")
    for instance in sonarr_instances:
        print(f"  Instance: {instance.name}")
        print(f"    Service Type: {instance.service_type} (raw: {type(instance.service_type)})")
        print(f"    Enabled: {instance.is_enabled}")
        print(f"    Default Movie: {instance.is_default_movie}")
        print(f"    Default TV: {instance.is_default_tv}")
        print(f"    Quality Tier: {instance.quality_tier}")
        print(f"    Category: {instance.instance_category}")
    
    session.close()
    
    print("\n" + "=" * 50)
    print("🔍 Debug complete!")

if __name__ == "__main__":
    asyncio.run(debug_movie_instance_issue())
