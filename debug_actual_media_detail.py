#!/usr/bin/env python3

import asyncio
import sys
sys.path.append('/opt/stoutRequests')

from app.core.database import get_session
from app.models.user import User
from sqlmodel import Session, select
from app.main import get_instances_for_media_type, create_template_response_with_instances
from fastapi import Request
from unittest.mock import Mock

async def debug_actual_media_detail():
    """Debug the ACTUAL media detail page call to find the real issue"""
    
    print("🔍 DEBUG: ACTUAL Media Detail Call")
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
    
    # Mock request object (like what media detail page would have)
    mock_request = Mock()
    mock_request.state = Mock()
    # Clear any potential cached instances to force fallback
    cache_key = f"user_instances_{admin_user.id}"
    if hasattr(mock_request.state, cache_key):
        delattr(mock_request.state, cache_key)
    
    # 1. Simulate what media detail endpoint does BEFORE calling template function
    print("\n🎥 1. BEFORE template function - endpoint gets instances:")
    
    # For a movie page
    media_type = "movie"
    available_instances = await get_instances_for_media_type(admin_user.id, media_type)
    print(f"  Endpoint got {len(available_instances)} instances for '{media_type}': {[i.name for i in available_instances]}")
    
    # 2. Build context like the media detail endpoint does
    context = {
        "request": mock_request,
        "current_user": admin_user,
        "media": {"id": 123, "title": "Test Movie", "media_type": "movie"},
        "media_type": media_type,
        "available_instances": available_instances  # This is what endpoint sets
    }
    
    print(f"\n📋 2. Context passed to template function:")
    print(f"  context['media_type']: {context.get('media_type')}")
    print(f"  context['available_instances']: {len(context.get('available_instances', []))} instances")
    print(f"  Available instances: {[i.name for i in context.get('available_instances', [])]}")
    
    # 3. Now let's see what create_template_response_with_instances does
    print(f"\n🧪 3. What create_template_response_with_instances does:")
    
    # Get the values the function would extract
    current_user = context.get('current_user')
    template_media_type = context.get('media_type', context.get('current_media_type', 'movie'))
    request = context.get('request')
    
    print(f"  current_user: {current_user.username if current_user else 'None'}")
    print(f"  template_media_type: '{template_media_type}'")
    print(f"  request: {request is not None}")
    print(f"  request.state exists: {hasattr(request, 'state') if request else False}")
    
    # Check for cached instances
    cache_key = f"user_instances_{current_user.id}"
    cached_instances = getattr(request.state, cache_key, None) if hasattr(request, 'state') else None
    print(f"  cached_instances: {cached_instances is not None}")
    
    if cached_instances:
        print(f"    Would use cached instances")
    else:
        print(f"    Would use fallback: get_user_instances_for_template_safe(user, '{template_media_type}')")
        
        # Test the fallback
        from app.main import get_user_instances_for_template_safe
        fallback_instances = await get_user_instances_for_template_safe(current_user, template_media_type)
        print(f"    Fallback returns: {len(fallback_instances)} instances - {[i.name for i in fallback_instances]}")
        
        # This is what would be put in enhanced_context
        print(f"\n💥 4. PROBLEM: Template function would OVERRIDE the correct instances!")
        print(f"  Original context had: {len(context.get('available_instances', []))} instances")
        print(f"  Template function sets: {len(fallback_instances)} instances")
        print(f"  Are they the same? {[i.name for i in context.get('available_instances', [])] == [i.name for i in fallback_instances]}")
    
    # 5. Test if it's ACTUALLY happening
    print(f"\n🧟 5. Let's ACTUALLY call the template function and see what happens:")
    
    # This is the EXACT call the media detail endpoint makes
    try:
        print(f"  Calling: create_template_response_with_instances('media_detail_simple.html', context)")
        result = await create_template_response_with_instances("media_detail_simple.html", {**context, "media_type": media_type})
        print(f"  Result type: {type(result)}")
        print(f"  SUCCESS: Template function executed without error")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    session.close()
    
    print("\n" + "=" * 50)
    print("🔍 ACTUAL media detail debug complete!")

if __name__ == "__main__":
    asyncio.run(debug_actual_media_detail())
