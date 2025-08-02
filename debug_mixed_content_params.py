#!/usr/bin/env python3

import asyncio
import sys
import os

# Add the app directory to Python path
sys.path.append('/opt/stoutRequests')

async def test_mixed_content_tmdb_service():
    """
    Test the TMDBService directly to verify mixed content is working properly
    """
    
    # Import the TMDBService
    from app.services.tmdb_service import TMDBService
    from app.database import get_session
    
    print("🔍 Testing TMDBService mixed content directly...")
    
    # Get a database session
    session = next(get_session())
    
    try:
        # Initialize TMDBService
        tmdb_service = TMDBService(session)
        
        # Test 1: Test discover_movies for page 2
        print("\n" + "="*60)
        print("🔍 TEST 1: discover_movies page 2")
        movie_results = tmdb_service.discover_movies(page=2, sort_by="popularity.desc")
        movies = movie_results.get('results', [])
        print(f"🎬 Got {len(movies)} movies on page 2")
        if movies:
            print(f"🎬 First movie: {movies[0].get('title', 'Unknown')}")
            print(f"🎬 Last movie: {movies[-1].get('title', 'Unknown')}")
        
        # Test 2: Test discover_tv for page 2
        print("\n" + "="*60)
        print("🔍 TEST 2: discover_tv page 2")
        tv_results = tmdb_service.discover_tv(page=2, sort_by="popularity.desc")
        tv_shows = tv_results.get('results', [])
        print(f"📺 Got {len(tv_shows)} TV shows on page 2")
        if tv_shows:
            print(f"📺 First TV show: {tv_shows[0].get('name', 'Unknown')}")
            print(f"📺 Last TV show: {tv_shows[-1].get('name', 'Unknown')}")
        
        # Test 3: Test get_category_content with mixed for page 2
        print("\n" + "="*60)
        print("🔍 TEST 3: get_category_content with media_type='mixed' page 2")
        try:
            mixed_results = tmdb_service.get_category_content(
                media_type="mixed",
                category="popular", 
                page=2
            )
            mixed_items = mixed_results.get('results', [])
            print(f"🎭 Got {len(mixed_items)} mixed items on page 2")
            
            movie_count = len([item for item in mixed_items if item.get('media_type') == 'movie'])
            tv_count = len([item for item in mixed_items if item.get('media_type') == 'tv'])
            
            print(f"🎬 Movies in mixed results: {movie_count}")
            print(f"📺 TV shows in mixed results: {tv_count}")
            
            if tv_count == 0:
                print("❌ BUG CONFIRMED: get_category_content for mixed type only returns movies!")
                
                # Let's debug the _get_mixed_content method
                print("\n🔍 Testing _get_mixed_content directly...")
                try:
                    direct_mixed = tmdb_service._get_mixed_content(
                        category="popular",
                        page=2
                    )
                    direct_items = direct_mixed.get('results', [])
                    direct_movie_count = len([item for item in direct_items if item.get('media_type') == 'movie'])
                    direct_tv_count = len([item for item in direct_items if item.get('media_type') == 'tv'])
                    
                    print(f"🔍 Direct _get_mixed_content - Movies: {direct_movie_count}, TV: {direct_tv_count}")
                    
                    if direct_tv_count == 0:
                        print("❌ BUG IS IN _get_mixed_content method!")
                    else:
                        print("✅ _get_mixed_content works correctly - bug is elsewhere")
                        
                except Exception as e:
                    print(f"❌ Error calling _get_mixed_content directly: {e}")
            else:
                print("✅ Mixed content working correctly in TMDBService")
                
        except Exception as e:
            print(f"❌ Error calling get_category_content with mixed: {e}")
            import traceback
            traceback.print_exc()
        
        # Test 4: Test the same logic as infinite scroll endpoint
        print("\n" + "="*60)
        print("🔍 TEST 4: Simulating infinite scroll logic")
        
        # Test the exact same parameters that infinite scroll would use
        media_type = "mixed"
        content_sources = []  # Empty content sources should trigger discover endpoint
        
        # This is the logic from discover_category_more
        use_discover_endpoint = (
            not content_sources or  # No sources selected
            len(content_sources) == 0  # Empty sources list
        )
        
        print(f"🔍 content_sources: {content_sources}")
        print(f"🔍 use_discover_endpoint: {use_discover_endpoint}")
        
        if use_discover_endpoint:
            print("🔍 Would use discover endpoint - testing that path...")
            
            # This is the mixed content logic from the endpoint
            if media_type == "mixed":
                print("🎯 Mixed media: fetching both movies and TV for page 2")
                
                # Fetch movies
                movie_response = tmdb_service.discover_movies(
                    page=2,
                    sort_by="popularity.desc"
                )
                movies_from_discover = movie_response.get('results', [])
                
                # Fetch TV shows
                tv_response = tmdb_service.discover_tv(
                    page=2,
                    sort_by="popularity.desc"
                )
                tv_from_discover = tv_response.get('results', [])
                
                print(f"🎬 Discover endpoint - Movies: {len(movies_from_discover)}")
                print(f"📺 Discover endpoint - TV: {len(tv_from_discover)}")
                
                if len(tv_from_discover) == 0:
                    print("❌ BUG: discover_tv returns no results!")
                else:
                    print("✅ Both movie and TV discovery working")
                    
                # Simulate the combining logic
                combined_results = []
                for item in movies_from_discover:
                    item['media_type'] = 'movie'
                    combined_results.append(item)
                for item in tv_from_discover:
                    item['media_type'] = 'tv'
                    combined_results.append(item)
                
                # Sort by popularity
                combined_results.sort(key=lambda x: x.get('popularity', 0), reverse=True)
                
                final_movie_count = len([item for item in combined_results if item.get('media_type') == 'movie'])
                final_tv_count = len([item for item in combined_results if item.get('media_type') == 'tv'])
                
                print(f"🎭 Final combined - Movies: {final_movie_count}, TV: {final_tv_count}")
        
    except Exception as e:
        print(f"❌ Error in TMDBService test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    print("🔍 Debug: TMDBService Mixed Content Testing")
    print("="*60)
    
    asyncio.run(test_mixed_content_tmdb_service())
    
    print("\n" + "="*60)
    print("🔍 Debug complete. Check the output above to identify the exact issue.")