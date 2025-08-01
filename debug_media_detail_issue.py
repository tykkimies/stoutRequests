#!/usr/bin/env python3

import asyncio
import sys
sys.path.append('/opt/stoutRequests')

from app.core.database import get_session
from app.models.user import User
from sqlmodel import Session, select
from app.main import get_instances_for_media_type
from fastapi import Request
from unittest.mock import Mock

async def debug_media_detail_issue():
    """Debug what media_type the template function is receiving"""
    
    print("🎥 DEBUG: Media Detail Template Issue")
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
    
    # 1. Test what the media detail endpoint gets
    print("\n🎥 1. What media detail endpoint gets (movies):")
    movie_instances = await get_instances_for_media_type(admin_user.id, "movie")
    print(f"  Movie instances: {len(movie_instances)} - {[i.name for i in movie_instances]}")
    
    print("\n📺 2. What media detail endpoint gets (TV):")
    tv_instances = await get_instances_for_media_type(admin_user.id, "tv")
    print(f"  TV instances: {len(tv_instances)} - {[i.name for i in tv_instances]}")
    
    # 2. Simulate what create_template_response_with_instances receives
    print("\n🔍 3. Simulating template function context:")
    
    # Mock request object
    mock_request = Mock()
    mock_request.state = Mock()
    
    # Test movie context (what media detail page would pass)
    movie_context = {
        'current_user': admin_user,
        'media_type': 'movie',  # This should make it get movie instances
        'request': mock_request,
        'available_instances': movie_instances  # Already set by endpoint
    }
    
    print(f"  Movie context media_type: {movie_context.get('media_type')}")
    print(f"  Movie context current_media_type: {movie_context.get('current_media_type', 'DEFAULT')}")
    print(f"  Movie context already has available_instances: {len(movie_context.get('available_instances', []))}")
    
    # Test what the template function's logic would determine
    media_type_determined = movie_context.get('media_type', movie_context.get('current_media_type', 'movie'))
    print(f"  Template function would use media_type: '{media_type_determined}'")
    
    # Test TV context
    tv_context = {
        'current_user': admin_user,
        'media_type': 'tv',  # This should make it get TV instances
        'request': mock_request,
        'available_instances': tv_instances  # Already set by endpoint
    }
    
    print(f"\n  TV context media_type: {tv_context.get('media_type')}")
    print(f"  TV context current_media_type: {tv_context.get('current_media_type', 'DEFAULT')}")
    print(f"  TV context already has available_instances: {len(tv_context.get('available_instances', []))}")
    
    # Test what the template function's logic would determine
    media_type_determined_tv = tv_context.get('media_type', tv_context.get('current_media_type', 'movie'))
    print(f"  Template function would use media_type: '{media_type_determined_tv}'")
    
    # 3. Test edge case - what if there's no cached instances?
    print("\n🤔 4. Testing no cached instances scenario:")
    print("  (This is probably what's happening)")
    
    # Clear any cached instances
    if hasattr(mock_request.state, f"user_instances_{admin_user.id}"):
        delattr(mock_request.state, f"user_instances_{admin_user.id}")
    
    # Test the fallback path
    from app.main import get_user_instances_for_template_safe
    
    print("\n  Testing fallback for movies:")
    fallback_movie_instances = await get_user_instances_for_template_safe(admin_user, 'movie')
    print(f"    Fallback movie instances: {len(fallback_movie_instances)} - {[i.name for i in fallback_movie_instances]}")
    
    print("\n  Testing fallback for TV:")
    fallback_tv_instances = await get_user_instances_for_template_safe(admin_user, 'tv')
    print(f"    Fallback TV instances: {len(fallback_tv_instances)} - {[i.name for i in fallback_tv_instances]}")
    
    session.close()
    
    print("\n" + "=" * 50)
    print("🎥 Media detail debug complete!")

if __name__ == "__main__":
    asyncio.run(debug_media_detail_issue())
