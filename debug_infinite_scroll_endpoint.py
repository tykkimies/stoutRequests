#!/usr/bin/env python3

"""
Debug script to simulate the discover_category_more endpoint call
to see what parameters are being passed and how they're processed.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlmodel import Session
from app.core.database import engine
from app.services.tmdb_service import TMDBService

def test_endpoint_parameters():
    """Test different parameter combinations that might be passed to discover_category_more."""
    
    print("🔍 TESTING DISCOVER_CATEGORY_MORE PARAMETER HANDLING")
    print("=" * 60)
    
    # Test scenarios based on the user's report
    test_scenarios = [
        {
            "name": "User's reported scenario",
            "params": {
                "type": "mixed",
                "media_type": "mixed", 
                "sort": "trending",
                "page": 2,
                "genres": ["28"]  # Action
            }
        },
        {
            "name": "Legacy type parameter only",
            "params": {
                "type": "mixed",
                "sort": "trending", 
                "page": 2,
                "genres": ["28"]
            }
        },
        {
            "name": "Media type parameter only",
            "params": {
                "media_type": "mixed",
                "sort": "trending",
                "page": 2, 
                "genres": ["28"]
            }
        },
        {
            "name": "Conflicting parameters",
            "params": {
                "type": "movie",
                "media_type": "mixed",
                "sort": "trending",
                "page": 2,
                "genres": ["28"]
            }
        }
    ]
    
    with Session(engine) as session:
        tmdb_service = TMDBService(session)
        
        for i, scenario in enumerate(test_scenarios, 1):
            print(f"\n🧪 SCENARIO {i}: {scenario['name']}")
            print("-" * 40)
            
            params = scenario["params"]
            
            # Simulate the logic from discover_category_more
            type_param = params.get("type")
            media_type_param = params.get("media_type")
            actual_media_type = media_type_param if media_type_param else type_param
            sort_param = params.get("sort", "trending")
            page = params.get("page", 1)
            genres = params.get("genres", [])
            
            print(f"📥 Input parameters:")
            print(f"  - type: '{type_param}'")
            print(f"  - media_type: '{media_type_param}'")
            print(f"  - sort: '{sort_param}'")
            print(f"  - page: {page}")
            print(f"  - genres: {genres}")
            
            print(f"\n🔄 Processing logic:")
            print(f"  - actual_media_type = '{actual_media_type}'")
            print(f"  - Is mixed content? {actual_media_type == 'mixed'}")
            
            if actual_media_type == "mixed":
                print(f"  ✅ Will call get_category_content with media_type='mixed'")
                
                try:
                    genre_filter = ",".join(genres) if genres else None
                    result = tmdb_service.get_category_content(
                        media_type=actual_media_type,
                        category=sort_param,
                        page=page,
                        with_genres=genre_filter
                    )
                    
                    results = result.get('results', [])
                    movie_count = len([r for r in results if r.get('media_type') == 'movie'])
                    tv_count = len([r for r in results if r.get('media_type') == 'tv'])
                    
                    print(f"  📊 Results: {len(results)} total ({movie_count} movies, {tv_count} TV shows)")
                    
                    if tv_count == 0 and movie_count > 0:
                        print(f"  ❌ BUG REPRODUCED: Only movies returned!")
                    elif tv_count > 0 and movie_count > 0:
                        print(f"  ✅ Working correctly: Mixed content returned")
                    
                except Exception as e:
                    print(f"  ❌ Error: {e}")
            else:
                print(f"  ⚠️  Will call single media type: '{actual_media_type}'")

if __name__ == "__main__":
    test_endpoint_parameters()