#!/usr/bin/env python3

"""
Debug script to test what happens when default query parameters are used
in the infinite scroll, which might explain why only movies are returned.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlmodel import Session
from app.core.database import engine
from app.services.tmdb_service import TMDBService

def test_default_query_params():
    """Test what happens with default query parameters."""
    
    print("🔍 TESTING DEFAULT QUERY PARAMETERS SCENARIO")
    print("=" * 60)
    
    # The template has this default: 'type=movie&sort=trending'
    # This means if current_query_params is empty or not set,
    # the infinite scroll will default to movie content only!
    
    test_scenarios = [
        {
            "name": "Default parameters from template",
            "description": "When current_query_params is empty, template defaults to 'type=movie&sort=trending'",
            "params": {
                "type": "movie",  # Default from template!
                "media_type": "",  # Default from endpoint
                "sort": "trending",
                "page": 2,
                "genres": ["28"]
            }
        },
        {
            "name": "Correct mixed content parameters",
            "description": "What should be passed for mixed content",
            "params": {
                "type": "mixed",
                "media_type": "mixed",
                "sort": "trending",
                "page": 2,
                "genres": ["28"]
            }
        },
        {
            "name": "URL with media_type but wrong type default",
            "description": "If URL has media_type=mixed but type defaults to movie",
            "params": {
                "type": "movie",  # Wrong default
                "media_type": "mixed",  # Correct
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
            print(f"📝 {scenario['description']}")
            print("-" * 50)
            
            params = scenario["params"]
            type_param = params["type"]
            media_type_param = params["media_type"]
            sort_param = params["sort"]
            page = params["page"]
            genres = params["genres"]
            
            # Apply the parameter precedence logic
            actual_media_type = media_type_param if media_type_param else type_param
            
            print(f"📥 Input parameters:")
            print(f"  - type: '{type_param}'")
            print(f"  - media_type: '{media_type_param}'")
            print(f"  - sort: '{sort_param}'")
            print(f"  - page: {page}")
            print(f"  - genres: {genres}")
            
            print(f"\n🔄 Processing:")
            print(f"  - actual_media_type = '{actual_media_type}'")
            print(f"  - Is mixed: {actual_media_type == 'mixed'}")
            
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
                
                print(f"\n📊 Results:")
                print(f"  - Total: {len(results)}")
                print(f"  - Movies: {movie_count}")
                print(f"  - TV shows: {tv_count}")
                
                if scenario["name"] == "Default parameters from template":
                    if tv_count == 0 and movie_count > 0:
                        print(f"  ❌ BUG FOUND: Default template parameters only return movies!")
                        print(f"  🔍 This explains the user's issue!")
                    else:
                        print(f"  ✅ Default parameters work correctly")
                elif actual_media_type == "mixed":
                    if tv_count == 0 and movie_count > 0:
                        print(f"  ❌ Mixed content not working")
                    elif tv_count > 0 and movie_count > 0:
                        print(f"  ✅ Mixed content working correctly")
                
            except Exception as e:
                print(f"  ❌ Error: {e}")

if __name__ == "__main__":
    test_default_query_params()