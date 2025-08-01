#!/usr/bin/env python3

import asyncio
import sys
sys.path.append('/opt/stoutRequests')

from app.core.database import get_session
from app.models.user import User
from sqlmodel import Session, select
from app.main import get_instances_for_media_type

async def debug_mixed_instances_issue():
    """Debug if template is somehow receiving mixed instances"""
    
    print("🌭 DEBUG: Mixed Instances Issue")
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
    
    # 1. Test all the different media types
    print("\n🧪 1. Testing different media_type calls:")
    
    for media_type in ['movie', 'tv', 'mixed', 'show', None, '']:
        print(f"\n  Testing media_type: '{media_type}'")
        try:
            instances = await get_instances_for_media_type(admin_user.id, media_type)
            print(f"    Result: {len(instances)} instances")
            for instance in instances:
                print(f"      - {instance.name}: {instance.service_type.value}")
        except Exception as e:
            print(f"    ERROR: {e}")
    
    # 2. Test the template macro filtering logic with mixed instances
    print("\n🧰 2. Testing macro filtering with mixed instances:")
    
    # Get both movie and TV instances
    movie_instances = await get_instances_for_media_type(admin_user.id, "movie")
    tv_instances = await get_instances_for_media_type(admin_user.id, "tv")
    mixed_instances = movie_instances + tv_instances
    
    print(f"  Movie instances: {len(movie_instances)} - {[i.name for i in movie_instances]}")
    print(f"  TV instances: {len(tv_instances)} - {[i.name for i in tv_instances]}")
    print(f"  Mixed instances: {len(mixed_instances)} - {[i.name for i in mixed_instances]}")
    
    # Simulate macro filtering for MOVIE item with MIXED instances
    print("\n  🎥 Filtering MIXED instances for MOVIE item:")
    item_media_type = 'movie'
    filtered_for_movie = []
    
    for instance in mixed_instances:
        condition = (item_media_type == 'movie' and instance.service_type.value == 'radarr')
        result = "PASS" if condition else "FAIL"
        print(f"    {instance.name} ({instance.service_type.value}): {result}")
        if condition:
            filtered_for_movie.append(instance)
    
    print(f"  📊 Final filtered instances for movie: {len(filtered_for_movie)}")
    if len(filtered_for_movie) == 0:
        print(f"    ❌ This would show 'No Access'!")
    else:
        print(f"    ✓ Would show {len(filtered_for_movie)} instance buttons")
    
    # Simulate macro filtering for TV item with MIXED instances
    print("\n  📺 Filtering MIXED instances for TV item:")
    item_media_type = 'tv'
    filtered_for_tv = []
    
    for instance in mixed_instances:
        condition = (item_media_type == 'tv' and instance.service_type.value == 'sonarr')
        result = "PASS" if condition else "FAIL"
        print(f"    {instance.name} ({instance.service_type.value}): {result}")
        if condition:
            filtered_for_tv.append(instance)
    
    print(f"  📊 Final filtered instances for TV: {len(filtered_for_tv)}")
    if len(filtered_for_tv) == 0:
        print(f"    ❌ This would show 'No Access'!")
    else:
        print(f"    ✓ Would show {len(filtered_for_tv)} instance buttons")
    
    # 3. Test if somehow the context is passing 'mixed' instead of 'movie'
    print("\n🤔 3. Hypothesis: What if context media_type is wrong?")
    
    # Test various context scenarios
    scenarios = [
        {'media_type': 'movie', 'current_media_type': None},
        {'media_type': None, 'current_media_type': 'movie'},
        {'media_type': 'mixed', 'current_media_type': None},
        {'media_type': None, 'current_media_type': 'mixed'},
        {'media_type': '', 'current_media_type': None},
        {}
    ]
    
    for i, context in enumerate(scenarios):
        media_type_determined = context.get('media_type', context.get('current_media_type', 'movie'))
        print(f"  Scenario {i+1}: {context} -> media_type: '{media_type_determined}'")
        
        if media_type_determined in ['mixed', '', None]:
            print(f"    ⚠️ This would call get_instances with mixed/empty media type!")
    
    session.close()
    
    print("\n" + "=" * 50)
    print("🌭 Mixed instances debug complete!")

if __name__ == "__main__":
    asyncio.run(debug_mixed_instances_issue())
