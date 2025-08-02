#!/usr/bin/env python3

"""
Debug script to simulate the complete request flow for discover_category_more
to see where the issue might be occurring.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlmodel import Session
from app.core.database import engine
from app.services.tmdb_service import TMDBService

def simulate_discover_category_more():
    """Simulate the discover_category_more endpoint logic step by step."""
    
    print("🔍 SIMULATING COMPLETE discover_category_more REQUEST FLOW")
    print("=" * 70)
    
    # Simulate the exact parameters that would come from the user's request
    # Based on the user's debug output showing:
    # - media_type='mixed'
    # - Action genre filter '28'
    # - Infinite scroll page 2
    
    print("📥 SIMULATED REQUEST PARAMETERS:")
    type_param = "mixed"
    media_type_param = "mixed"
    sort_param = "trending"
    page = 2
    genres = ["28"]  # Action genre
    rating_min = ""
    rating_source = "tmdb"
    year_from = ""
    year_to = ""
    studios = []
    streaming = []
    limit = 20
    
    print(f"  - type: '{type_param}'")
    print(f"  - media_type: '{media_type_param}'")
    print(f"  - sort: '{sort_param}'")
    print(f"  - page: {page}")
    print(f"  - genres: {genres}")
    print(f"  - Other filters: rating_min='{rating_min}', year_from='{year_from}', year_to='{year_to}'")
    print()
    
    with Session(engine) as session:
        try:
            # Step 1: Initialize TMDBService
            print("🔧 STEP 1: Initialize TMDBService")
            tmdb_service = TMDBService(session)
            print("  ✅ TMDBService initialized")
            
            # Step 2: Parameter precedence logic
            print("\n🔧 STEP 2: Parameter precedence logic")
            actual_media_type = media_type_param if media_type_param else type_param
            print(f"  - actual_media_type = '{actual_media_type}'")
            print(f"  - Is mixed content? {actual_media_type == 'mixed'}")
            
            # Step 3: Filter processing
            print("\n🔧 STEP 3: Filter processing")
            genre_filter = ",".join(genres) if genres else None
            rating_filter = None  # convert_rating_to_tmdb_filter would be called here
            year_from_filter = int(year_from) if year_from else None
            year_to_filter = int(year_to) if year_to else None
            company_filter = None
            streaming_filter = None
            
            print(f"  - genre_filter: '{genre_filter}'")
            print(f"  - rating_filter: {rating_filter}")
            print(f"  - year filters: {year_from_filter} to {year_to_filter}")
            
            # Step 4: Check if this takes a different path (database categories, custom categories, etc.)
            print("\n🔧 STEP 4: Route determination")
            # These would normally come from query parameters
            db_category_type = None
            db_category_sort = None
            custom_category_id = None
            
            if db_category_type and db_category_sort:
                print("  🔀 Would take DATABASE category path")
                return
            elif custom_category_id:
                print("  🔀 Would take CUSTOM category path")
                return
            else:
                print("  🔀 Taking TMDB API category path")
            
            # Step 5: Date parameter mapping for mixed content
            print("\n🔧 STEP 5: Date parameter mapping for mixed content")
            if actual_media_type == "mixed":
                movie_date_gte = year_from_filter
                movie_date_lte = year_to_filter
                tv_date_gte = year_from_filter
                tv_date_lte = year_to_filter
            elif actual_media_type == "movie":
                movie_date_gte = year_from_filter
                movie_date_lte = year_to_filter
                tv_date_gte = None
                tv_date_lte = None
            else:  # tv
                movie_date_gte = None
                movie_date_lte = None
                tv_date_gte = year_from_filter
                tv_date_lte = year_to_filter
                
            print(f"  - movie_date_gte/lte: {movie_date_gte}/{movie_date_lte}")
            print(f"  - tv_date_gte/lte: {tv_date_gte}/{tv_date_lte}")
            
            # Step 6: Call get_category_content
            print("\n🔧 STEP 6: Call tmdb_service.get_category_content")
            print(f"  - Calling with media_type='{actual_media_type}', category='{sort_param}', page={page}")
            
            data = tmdb_service.get_category_content(
                media_type=actual_media_type,
                category=sort_param,
                page=page,
                with_genres=genre_filter,
                vote_average_gte=rating_filter,
                with_companies=company_filter,
                with_networks=None,
                with_watch_providers=streaming_filter,
                primary_release_date_gte=movie_date_gte,
                primary_release_date_lte=movie_date_lte,
                first_air_date_gte=tv_date_gte,
                first_air_date_lte=tv_date_lte
            )
            
            results = data.get('results', [])
            total_pages = data.get('total_pages', 1)
            
            print(f"  ✅ get_category_content completed")
            print(f"  - Returned {len(results)} results")
            print(f"  - Total pages: {total_pages}")
            
            # Step 7: Media type assignment for results
            print("\n🔧 STEP 7: Media type assignment for results")
            print(f"  - Processing {len(results)} results...")
            
            for item in results:
                if 'media_type' not in item or item.get('media_type') is None:
                    if actual_media_type == "mixed":
                        # For mixed content, determine media_type from TMDB data structure
                        if 'title' in item and 'release_date' in item:
                            item['media_type'] = 'movie'
                        elif 'name' in item and 'first_air_date' in item:
                            item['media_type'] = 'tv'
                        else:
                            # Fallback based on which fields are present
                            item['media_type'] = 'movie' if 'title' in item else 'tv'
                    else:
                        item['media_type'] = actual_media_type
            
            # Step 8: Final analysis
            print("\n🔧 STEP 8: Final result analysis")
            movie_count = len([r for r in results if r.get('media_type') == 'movie'])
            tv_count = len([r for r in results if r.get('media_type') == 'tv'])
            unknown_count = len([r for r in results if r.get('media_type') not in ['movie', 'tv']])
            
            print(f"  - Total results: {len(results)}")
            print(f"  - Movies: {movie_count}")
            print(f"  - TV shows: {tv_count}")
            print(f"  - Unknown media type: {unknown_count}")
            
            if tv_count == 0 and movie_count > 0:
                print(f"\n❌ BUG REPRODUCED: Only movies returned in infinite scroll!")
                print(f"This confirms the reported issue.")
            elif tv_count > 0 and movie_count > 0:
                print(f"\n✅ WORKING CORRECTLY: Mixed content returned as expected")
            else:
                print(f"\n⚠️  UNEXPECTED RESULT: movie_count={movie_count}, tv_count={tv_count}")
            
            # Show sample results
            print(f"\n📝 SAMPLE RESULTS:")
            for i, item in enumerate(results[:5]):
                title = item.get('title', item.get('name', 'Unknown'))
                media_type = item.get('media_type', 'NOT SET')
                print(f"  [{i+1}] {title} -> {media_type}")
            
        except Exception as e:
            print(f"\n❌ ERROR in simulation: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    simulate_discover_category_more()