#!/usr/bin/env python3

import sys
sys.path.append('/opt/stoutRequests')

from jinja2 import Environment, FileSystemLoader
from app.models.service_instance import ServiceType

def test_multi_instance_button_fix():
    """Test that the multi-instance button macro correctly filters instances."""
    print("🔧 Testing Multi-Instance Button Fix")
    print("=" * 50)
    
    # Create mock instances with correct ServiceType enum values
    class MockInstance:
        def __init__(self, id, name, service_type, quality_tier="standard"):
            self.id = id
            self.name = name
            self.service_type = service_type  # Store enum directly, not .value
            self.quality_tier = quality_tier
            self.instance_category = None
    
    radarr_instance = MockInstance(1, "Radarr 4K", ServiceType.RADARR, "4k")
    sonarr_instance = MockInstance(2, "Sonarr HD", ServiceType.SONARR, "standard")
    
    available_instances = [radarr_instance, sonarr_instance]
    
    print(f"📋 Test Data:")
    print(f"  Available instances: {len(available_instances)}")
    for inst in available_instances:
        print(f"    - {inst.name}: {inst.service_type} (enum value: '{inst.service_type.value}')")
    
    # Load the Jinja2 template environment
    template_dir = "/opt/stoutRequests/app/templates"
    env = Environment(loader=FileSystemLoader(template_dir))
    
    # Load the macro template
    macro_template = env.get_template("macros/multi_instance_request.html")
    
    # Create a test template that uses the macro
    test_template_str = """
{%- from 'macros/multi_instance_request.html' import multi_instance_request_button -%}

<!-- Test Movie Button -->
<div id="movie-test">
{{ multi_instance_request_button(
    item, 
    None, 
    available_instances, 
    style='button', 
    size='md', 
    status=None,
    tmdb_id=movie_id,
    media_type='movie',
    base_url=''
) }}
</div>

<!-- Test TV Button -->
<div id="tv-test">
{{ multi_instance_request_button(
    item, 
    None, 
    available_instances, 
    style='button', 
    size='md', 
    status=None,
    tmdb_id=tv_id,
    media_type='tv',
    base_url=''
) }}
</div>
"""
    
    test_template = env.from_string(test_template_str)
    
    # Create mock item objects
    class MockItem:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    movie_item = MockItem(
        id=12345,
        title="Test Movie",
        media_type="movie",
        poster_path="/test.jpg"
    )
    
    tv_item = MockItem(
        id=67890,
        name="Test TV Show",
        media_type="tv",
        poster_path="/test-tv.jpg"
    )
    
    # Test movie rendering
    print("\n🎬 Testing Movie Request Button:")
    try:
        movie_result = test_template.render(
            item=movie_item,
            available_instances=available_instances,
            movie_id=12345,
            tv_id=67890
        )
        
        # Extract just the movie section
        movie_section = movie_result.split('<div id="movie-test">')[1].split('</div>')[0]
        print(f"  ✅ Movie macro rendered successfully")
        
        if "No Access" in movie_section:
            print(f"  ❌ ERROR: Movie button shows 'No Access' - filtering failed!")
            print(f"    This means Radarr instance was not found for movie request")
        elif "Request" in movie_section and ("form" in movie_section or "button" in movie_section):
            print(f"  ✅ SUCCESS: Movie button shows request options (Radarr instance found)")
        else:
            print(f"  ❓ Movie button content unclear")
            
    except Exception as e:
        print(f"  ❌ Movie macro failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test TV rendering
    print("\n📺 Testing TV Show Request Button:")
    try:
        tv_section = movie_result.split('<div id="tv-test">')[1].split('</div>')[0]
        print(f"  ✅ TV macro rendered successfully")
        
        if "No Access" in tv_section:
            print(f"  ❌ ERROR: TV button shows 'No Access' - filtering failed!")
            print(f"    This means Sonarr instance was not found for TV request")
        elif "Request" in tv_section and ("form" in tv_section or "button" in tv_section):
            print(f"  ✅ SUCCESS: TV button shows request options (Sonarr instance found)")
        else:
            print(f"  ❓ TV button content unclear")
            
    except Exception as e:
        print(f"  ❌ TV macro failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 50)
    print("🎯 Fix Summary:")
    print("  - Fixed service_type.value → service_type in macro filtering")
    print("  - ServiceType enum values are compared directly")
    print("  - Movie requests should now find Radarr instances")
    print("  - TV requests should now find Sonarr instances")
    print("  - Main request buttons should no longer show 'No Access' incorrectly")
    
    print("\n📝 Debug Info:")
    print(f"  - ServiceType.RADARR = '{ServiceType.RADARR}'")
    print(f"  - ServiceType.SONARR = '{ServiceType.SONARR}'")
    print(f"  - Direct comparison works: {ServiceType.RADARR == 'radarr'}")
    print(f"  - Direct comparison works: {ServiceType.SONARR == 'sonarr'}")

if __name__ == "__main__":
    test_multi_instance_button_fix()
