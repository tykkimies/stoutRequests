#!/usr/bin/env python3
"""
Test script to verify the genre mapping fix for custom categories.
This tests the critical issue where Action genre (ID 28) was not working for TV shows.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.tmdb_service import TMDBService
from app.core.database import engine
from sqlmodel import Session

def test_genre_mapping():
    """Test the genre mapping functionality"""
    print("🧪 Testing Genre Mapping Fix")
    print("=" * 50)
    
    with Session(engine) as session:
        tmdb_service = TMDBService(session)
        
        # Test cases based on research findings
        test_cases = [
            {
                'name': 'Action Genre (Main Issue)',
                'input': '28',  # Movie Action ID
                'expected_movie': '28',  # Should stay as Action for movies
                'expected_tv': '10759'   # Should map to Action & Adventure for TV
            },
            {
                'name': 'Adventure Genre',
                'input': '12',  # Movie Adventure ID
                'expected_movie': '12',  # Should stay as Adventure for movies
                'expected_tv': '10759'   # Should map to Action & Adventure for TV
            },
            {
                'name': 'Science Fiction Genre',
                'input': '878',  # Movie Sci-Fi ID
                'expected_movie': '878',  # Should stay as Science Fiction for movies
                'expected_tv': '10765'   # Should map to Sci-Fi & Fantasy for TV
            },
            {
                'name': 'Fantasy Genre',
                'input': '14',  # Movie Fantasy ID  
                'expected_movie': '14',  # Should stay as Fantasy for movies
                'expected_tv': '10765'   # Should map to Sci-Fi & Fantasy for TV
            },
            {
                'name': 'War Genre',
                'input': '10752',  # Movie War ID
                'expected_movie': '10752',  # Should stay as War for movies
                'expected_tv': '10768'     # Should map to War & Politics for TV
            },
            {
                'name': 'Comedy Genre (Direct Match)',
                'input': '35',  # Comedy ID (same for both)
                'expected_movie': '35',  # Should stay as Comedy for movies
                'expected_tv': '35'      # Should stay as Comedy for TV
            },
            {
                'name': 'TV-only Genre (Talk)',
                'input': '10767',  # TV Talk ID
                'expected_movie': None,    # Should not map to any movie genre
                'expected_tv': '10767'     # Should stay as Talk for TV
            },
            {
                'name': 'Movie-only Genre (Romance)',
                'input': '10749',  # Movie Romance ID
                'expected_movie': '10749',  # Should stay as Romance for movies
                'expected_tv': None        # Should not map to any TV genre
            },
            {
                'name': 'Multiple Genres (Action + Comedy)',
                'input': '28,35',  # Action + Comedy
                'expected_movie': '28,35',      # Action + Comedy for movies
                'expected_tv': '10759,35'       # Action & Adventure + Comedy for TV
            },
            {
                'name': 'Reverse Mapping (TV Action & Adventure to Movie)',
                'input': '10759',  # TV Action & Adventure ID
                'expected_movie': '28',      # Should map to Action for movies
                'expected_tv': '10759'       # Should stay as Action & Adventure for TV
            }
        ]
        
        # Run test cases
        all_passed = True
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n{i}. {test_case['name']}")
            print(f"   Input: {test_case['input']}")
            
            try:
                movie_result, tv_result = tmdb_service._map_genres_for_mixed_content(test_case['input'])
                
                print(f"   Result - Movies: {movie_result}, TV: {tv_result}")
                print(f"   Expected - Movies: {test_case['expected_movie']}, TV: {test_case['expected_tv']}")
                
                # Check results
                movie_match = movie_result == test_case['expected_movie']
                tv_match = tv_result == test_case['expected_tv']
                
                if movie_match and tv_match:
                    print(f"   ✅ PASSED")
                else:
                    print(f"   ❌ FAILED")
                    if not movie_match:
                        print(f"      Movie mismatch: got {movie_result}, expected {test_case['expected_movie']}")
                    if not tv_match:
                        print(f"      TV mismatch: got {tv_result}, expected {test_case['expected_tv']}")
                    all_passed = False
                    
            except Exception as e:
                print(f"   ❌ ERROR: {e}")
                all_passed = False
        
        print("\n" + "=" * 50)
        if all_passed:
            print("🎉 ALL TESTS PASSED! Genre mapping fix is working correctly.")
        else:
            print("💥 SOME TESTS FAILED! Check the implementation.")
        print("=" * 50)

def test_real_api_calls():
    """Test actual API calls to verify the fix works end-to-end"""
    print("\n🌐 Testing Real API Calls")
    print("=" * 50)
    
    with Session(engine) as session:
        tmdb_service = TMDBService(session)
        
        # Test the exact scenario from the issue: Action genre in mixed content
        print("Testing Action genre (ID 28) in mixed content...")
        
        try:
            # This should now work correctly for both movies and TV shows
            result = tmdb_service.get_category_content(
                media_type="mixed",
                category="popular", 
                page=1,
                with_genres="28"  # Action genre
            )
            
            movies_found = len([r for r in result.get('results', []) if r.get('media_type') == 'movie'])
            tv_found = len([r for r in result.get('results', []) if r.get('media_type') == 'tv'])
            
            print(f"Results: {len(result.get('results', []))} total ({movies_found} movies, {tv_found} TV shows)")
            
            if movies_found > 0 and tv_found > 0:
                print("✅ SUCCESS: Both movies and TV shows returned for Action genre!")
                print("🎯 This confirms the genre mapping fix is working!")
            elif movies_found > 0 and tv_found == 0:
                print("⚠️ PARTIAL: Only movies returned - TV genre mapping may not be working")
            elif movies_found == 0 and tv_found > 0:
                print("⚠️ PARTIAL: Only TV shows returned - movie genre mapping may not be working")
            else:
                print("❌ FAILED: No results returned")
                
        except Exception as e:
            print(f"❌ API ERROR: {e}")

if __name__ == "__main__":
    test_genre_mapping()
    test_real_api_calls()