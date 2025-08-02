#!/usr/bin/env python3

"""
Debug script to specifically test what happens when we get movie-only results.
This will help confirm if the issue is frontend parameter passing.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlmodel import Session
from app.core.database import engine
from app.services.tmdb_service import TMDBService

def test_movie_only_scenario():
    """Test what happens when only movie parameters are passed."""
    
    print("🔍 TESTING MOVIE-ONLY SCENARIO (POTENTIAL USER ISSUE)")
    print("=" * 60)
    
    with Session(engine) as session:
        tmdb_service = TMDBService(session)
        
        # This simulates what might happen if current_query_params is not
        # properly set in the template, causing the default to be used
        print("🧪 Testing: type='movie', media_type='', sort='trending', page=2")
        print("📝 This happens when template uses default: 'type=movie&sort=trending'")
        print()
        
        try:
            # The parameter precedence logic
            type_param = "movie"
            media_type_param = ""  # Empty string (template default)
            actual_media_type = media_type_param if media_type_param else type_param
            
            print(f"🔄 Parameter precedence:")
            print(f"  - type: '{type_param}'")
            print(f"  - media_type: '{media_type_param}' (empty string)")
            print(f"  - actual_media_type = '{actual_media_type}'")
            print(f"  - Will use single media type: {actual_media_type}")
            print()
            
            # Call the service
            result = tmdb_service.get_category_content(
                media_type=actual_media_type,  # This will be "movie"
                category="trending",
                page=2,
                with_genres="28"  # Action genre
            )
            
            results = result.get('results', [])
            print(f"📊 Results:")
            print(f"  - Total results: {len(results)}")
            
            # Count by inspecting the actual structure since media_type isn't set yet
            movie_count = 0
            tv_count = 0
            for item in results:
                # Check the data structure to determine media type
                if 'title' in item and 'release_date' in item:
                    movie_count += 1
                    item['media_type'] = 'movie'  # Set it for display
                elif 'name' in item and 'first_air_date' in item:
                    tv_count += 1
                    item['media_type'] = 'tv'  # Set it for display
                else:
                    # Fallback
                    if 'title' in item:
                        movie_count += 1
                        item['media_type'] = 'movie'
                    else:
                        tv_count += 1
                        item['media_type'] = 'tv'
            
            print(f"  - Movies: {movie_count}")
            print(f"  - TV shows: {tv_count}")
            
            if tv_count == 0 and movie_count > 0:
                print(f"\n❌ CONFIRMED: Only movies returned!")
                print(f"🔍 This is exactly what the user is experiencing!")
                print(f"💡 The issue is likely that current_query_params is not properly")
                print(f"   preserving the media_type=mixed parameter for infinite scroll.")
            
            print(f"\n📝 Sample results:")
            for i, item in enumerate(results[:3]):
                title = item.get('title', item.get('name', 'Unknown'))
                media_type = item.get('media_type', 'NOT SET')
                fields = []
                if 'title' in item:
                    fields.append('title')
                if 'name' in item:
                    fields.append('name')
                if 'release_date' in item:
                    fields.append('release_date')
                if 'first_air_date' in item:
                    fields.append('first_air_date')
                print(f"  [{i+1}] {title} -> {media_type} (fields: {', '.join(fields)})")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_movie_only_scenario()