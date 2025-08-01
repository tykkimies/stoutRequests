#!/usr/bin/env python3

import asyncio
import sys
sys.path.append('/opt/stoutRequests')

from app.core.database import get_session
from app.models.user import User
from app.models.service_instance import ServiceInstance, ServiceType
from app.main import get_instances_for_media_type
from sqlmodel import Session, select

async def debug_template_movie_issue():
    """Debug the template macro filtering logic specifically"""
    
    print("🎨 DEBUG: Template Movie Issue Analysis")
    print("=" * 50)
    
    # Get database session
    session = next(get_session()) 
    
    # Get admin user
    users_stmt = select(User).where(User.is_admin == True)
    admin_users = session.exec(users_stmt).all()
    admin_user = admin_users[0] if admin_users else None
    
    if not admin_user:
        print("❌ No admin user found")
        return
    
    print(f"👤 Using admin user: {admin_user.username}")
    
    # 1. Get instances that template would receive
    print("\n🧪 1. Instances template would receive:")
    movie_instances = await get_instances_for_media_type(admin_user.id, "movie")
    tv_instances = await get_instances_for_media_type(admin_user.id, "tv")
    
    print(f"  available_instances for movies: {len(movie_instances)}")
    for instance in movie_instances:
        print(f"    - {instance.name}: service_type={instance.service_type.value}")
    
    print(f"  available_instances for TV: {len(tv_instances)}")
    for instance in tv_instances:
        print(f"    - {instance.name}: service_type={instance.service_type.value}")
    
    # 2. Simulate the macro filtering logic
    print("\n🧰 2. Simulating macro filtering logic:")
    
    # For a movie item
    print("\n  For MOVIE item (item_media_type='movie'):")
    item_media_type = 'movie'
    filtered_instances_movie = []
    
    for instance in movie_instances:
        condition = (item_media_type == 'movie' and instance.service_type.value == 'radarr')
        print(f"    Instance '{instance.name}': media_type={item_media_type}, service_type={instance.service_type.value}, condition={condition}")
        if condition:
            filtered_instances_movie.append(instance)
    
    print(f"  📊 Filtered movie instances: {len(filtered_instances_movie)}")
    if filtered_instances_movie:
        for instance in filtered_instances_movie:
            print(f"    ✓ {instance.name}")
    else:
        print("    ❌ No instances passed filter - would show 'No Access'")
    
    # For a TV item 
    print("\n  For TV item (item_media_type='tv'):")
    item_media_type = 'tv'
    filtered_instances_tv = []
    
    for instance in tv_instances:
        condition = (item_media_type == 'tv' and instance.service_type.value == 'sonarr')
        print(f"    Instance '{instance.name}': media_type={item_media_type}, service_type={instance.service_type.value}, condition={condition}")
        if condition:
            filtered_instances_tv.append(instance)
    
    print(f"  📊 Filtered TV instances: {len(filtered_instances_tv)}")
    if filtered_instances_tv:
        for instance in filtered_instances_tv:
            print(f"    ✓ {instance.name}")
    else:
        print("    ❌ No instances passed filter - would show 'No Access'")
    
    # 3. Check what happens if we pass mixed instances to movie filtering
    print("\n🤔 3. What if movie template receives MIXED instances?")
    
    # Simulate getting mixed instances (this might be the bug)
    mixed_instances = movie_instances + tv_instances
    print(f"  Mixed instances total: {len(mixed_instances)}")
    
    print("\n  Filtering mixed instances for MOVIE:")
    item_media_type = 'movie'
    filtered_mixed_for_movie = []
    
    for instance in mixed_instances:
        condition = (item_media_type == 'movie' and instance.service_type.value == 'radarr')
        print(f"    Instance '{instance.name}': service_type={instance.service_type.value}, condition={condition}")
        if condition:
            filtered_mixed_for_movie.append(instance)
    
    print(f"  📊 Filtered mixed instances for movie: {len(filtered_mixed_for_movie)}")
    
    # 4. Check service type enum values
    print("\n🔢 4. Service Type Enum Values:")
    print(f"  ServiceType.RADARR: {ServiceType.RADARR}")
    print(f"  ServiceType.SONARR: {ServiceType.SONARR}")
    print(f"  ServiceType.RADARR.value: {ServiceType.RADARR.value}")
    print(f"  ServiceType.SONARR.value: {ServiceType.SONARR.value}")
    
    session.close()
    
    print("\n" + "=" * 50)
    print("🎨 Template debug complete!")

if __name__ == "__main__":
    asyncio.run(debug_template_movie_issue())
