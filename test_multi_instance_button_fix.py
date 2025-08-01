#!/usr/bin/env python3

import asyncio
import sys
import os
sys.path.append('/opt/stoutRequests')

from app.models import User, ServiceInstance, ServiceType
from app.services.instance_selection_service import get_instance_selection_service
from app.core.template_context import create_template_response_with_instances
from jinja2 import Environment, FileSystemLoader
from sqlmodel import Session, create_engine
from app.core.database import get_session, init_db

async def test_multi_instance_button_fix():
    """Test that the multi-instance button macro correctly filters instances."""
    print("🔧 Testing Multi-Instance Button Fix")
    print("=" * 50)
    
    # Create test user
    test_user = User(
        id=1,
        plex_username="test_user",
        email="test@example.com",
        is_admin=False
    )
    
    # Create test instances with correct ServiceType enum values
    radarr_instance = ServiceInstance(
        id=1,
        name="Radarr 4K",
        service_type=ServiceType.RADARR,  # This is the enum, not .value
        url="http://radarr:7878",
        api_key="test-key",
        quality_tier="4k"
    )
    
    sonarr_instance = ServiceInstance(
        id=2,
        name="Sonarr HD", 
        service_type=ServiceType.SONARR,  # This is the enum, not .value
        url="http://sonarr:8989",
        api_key="test-key",
        quality_tier="standard"
    )
    
    available_instances = [radarr_instance, sonarr_instance]
    
    print(f"📋 Test Data:")
    print(f"  Available instances: {len(available_instances)}")
    for inst in available_instances:
        print(f"    - {inst.name}: {inst.service_type} (type: {type(inst.service_type)})")
    
    # Load the Jinja2 template environment
    template_dir = "/opt/stoutRequests/app/templates"
    env = Environment(loader=FileSystemLoader(template_dir))
    
    # Load the macro template
    macro_template = env.get_template("macros/multi_instance_request.html")
    
    # Test movie item filtering
    print("\n🎬 Testing Movie Request Button:")
    movie_item = {
        "id": 12345,
        "title": "Test Movie",
        "media_type": "movie",
        "poster_path": "/test.jpg"
    }
    
    # Render the macro for a movie
    try:
        movie_result = macro_template.module.multi_instance_request_button(
            item=type('Item', (), movie_item),
            user_permissions=None,
            available_instances=available_instances,
            style='button',
            size='md',
            status=None,
            tmdb_id=12345,
            media_type='movie',
            base_url=''
        )
        print(f"  ✅ Movie macro rendered successfully")
        print(f"  📊 Result length: {len(movie_result)} characters")
        if "No Access" in movie_result:
            print(f"  ❌ ERROR: Movie button shows 'No Access' - filtering failed")
        else:
            print(f"  ✅ Movie button shows request options (Radarr instance found)")
    except Exception as e:
        print(f"  ❌ Movie macro failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test TV show item filtering  
    print("\n📺 Testing TV Show Request Button:")
    tv_item = {
        "id": 67890,
        "name": "Test TV Show",
        "media_type": "tv",
        "poster_path": "/test-tv.jpg"
    }
    
    try:
        tv_result = macro_template.module.multi_instance_request_button(
            item=type('Item', (), tv_item),
            user_permissions=None,
            available_instances=available_instances,
            style='button', 
            size='md',
            status=None,
            tmdb_id=67890,
            media_type='tv',
            base_url=''
        )
        print(f"  ✅ TV macro rendered successfully")
        print(f"  📊 Result length: {len(tv_result)} characters")
        if "No Access" in tv_result:
            print(f"  ❌ ERROR: TV button shows 'No Access' - filtering failed")
        else:
            print(f"  ✅ TV button shows request options (Sonarr instance found)")
    except Exception as e:
        print(f"  ❌ TV macro failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test edge case: no instances for media type
    print("\n🚫 Testing No Available Instances:")
    empty_instances = []
    try:
        no_instance_result = macro_template.module.multi_instance_request_button(
            item=type('Item', (), movie_item),
            user_permissions=None,
            available_instances=empty_instances,
            style='button',
            size='md', 
            status=None,
            tmdb_id=12345,
            media_type='movie',
            base_url=''
        )
        print(f"  ✅ No instances macro rendered successfully")
        if "No Access" in no_instance_result:
            print(f"  ✅ Correctly shows 'No Access' when no instances available")
        else:
            print(f"  ❌ ERROR: Should show 'No Access' when no instances available")
    except Exception as e:
        print(f"  ❌ No instances macro failed: {e}")
    
    print("\n" + "=" * 50)
    print("🎯 Fix Summary:")
    print("  - Fixed service_type.value → service_type in macro filtering")
    print("  - ServiceType enum values are stored directly, not in .value property")
    print("  - Movie requests should now find Radarr instances")
    print("  - TV requests should now find Sonarr instances")
    print("  - Main request buttons should no longer show 'No Access' incorrectly")

if __name__ == "__main__":
    asyncio.run(test_multi_instance_button_fix())
