#!/usr/bin/env python3

"""
Debug script to test the build_discover_query_params function
and see what query parameters it generates.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the function from main.py
from app.main import build_discover_query_params

def test_query_params_building():
    """Test the build_discover_query_params function with different scenarios."""
    
    print("🔍 TESTING build_discover_query_params FUNCTION")
    print("=" * 60)
    
    test_scenarios = [
        {
            "name": "Mixed content with action genre",
            "params": {
                "media_type": "mixed",
                "type": "mixed",
                "sort": "trending",
                "genres": ["28"],
                "rating_source": "tmdb",
                "rating_min": "",
                "year_from": "",
                "year_to": "",
                "studios": [],
                "streaming": [],
                "limit": 20
            }
        },
        {
            "name": "Empty media_type (should use type)",
            "params": {
                "media_type": "",
                "type": "mixed",
                "sort": "trending",
                "genres": ["28"],
                "limit": 20
            }
        },
        {
            "name": "None media_type (should use type)",
            "params": {
                "media_type": None,
                "type": "mixed",
                "sort": "trending",
                "genres": ["28"],
                "limit": 20
            }
        },
        {
            "name": "Default movie type",
            "params": {
                "media_type": "movie",
                "type": "movie",
                "sort": "trending",
                "genres": ["28"],
                "limit": 20
            }
        }
    ]
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n🧪 SCENARIO {i}: {scenario['name']}")
        print("-" * 40)
        
        params = scenario["params"]
        print(f"📥 Input parameters:")
        for key, value in params.items():
            print(f"  - {key}: {repr(value)}")
        
        try:
            # Call the function
            query_string = build_discover_query_params(**params)
            
            print(f"\n📤 Generated query string:")
            print(f"  '{query_string}'")
            
            # Parse and analyze the query string
            if query_string:
                query_parts = query_string.split('&')
                print(f"\n🔍 Query parameters breakdown:")
                for part in query_parts:
                    print(f"  - {part}")
                
                # Check if media_type is included
                media_type_included = any(part.startswith('media_type=') for part in query_parts)
                type_included = any(part.startswith('type=') for part in query_parts)
                
                print(f"\n📊 Analysis:")
                print(f"  - media_type parameter included: {media_type_included}")
                print(f"  - type parameter included: {type_included}")
                
                if scenario['name'] == "Mixed content with action genre":
                    if not media_type_included:
                        print(f"  ❌ BUG: media_type=mixed not included in query string!")
                        print(f"  🔍 This would cause infinite scroll to fail!")
                    else:
                        # Extract the media_type value
                        media_type_param = next((part for part in query_parts if part.startswith('media_type=')), None)
                        if media_type_param == 'media_type=mixed':
                            print(f"  ✅ Correct: media_type=mixed is included")
                        else:
                            print(f"  ❌ Wrong: {media_type_param} instead of media_type=mixed")
            else:
                print(f"  ❌ ERROR: Empty query string generated!")
            
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_query_params_building()