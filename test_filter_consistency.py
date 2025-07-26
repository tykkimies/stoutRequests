#!/usr/bin/env python3
"""
Test the exact user scenario: filter inconsistency when applying additional filters.
Reproduces the bug where Movie X disappears when adding adventure genre filter.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.tmdb_service import TMDBService

def test_filter_consistency_bug():
    """Test the exact scenario described by the user"""
    
    print("🎯 Testing Filter Consistency Bug")
    print("=" * 70)
    print("Scenario: User filters All media + 2024-2025 dates, then adds adventure genre")
    print("Expected: Movie X should still appear in results")
    print("Bug: Movie X disappears and results reorder unexpectedly")
    print("=" * 70)
    
    tmdb_service = TMDBService()
    
    # Step 1: Initial filter - All media + dates 2024-2025
    print("\n📅 STEP 1: Filter by All media + dates 2024-2025")
    
    initial_results = tmdb_service._get_mixed_content(
        category="popular",
        page=1,
        primary_release_date_gte="2024-01-01",
        primary_release_date_lte="2025-12-31",
        first_air_date_gte="2024-01-01",
        first_air_date_lte="2025-12-31"
    )
    
    initial_items = initial_results.get('results', [])
    print(f"   📊 Initial results: {len(initial_items)} items")
    
    if not initial_items:
        print("   ⚠️  No initial results - cannot test filter consistency")
        return False
    
    # Show first few items with their details
    print("   📋 First 5 items:")
    for i, item in enumerate(initial_items[:5]):
        title = item.get('title') or item.get('name', 'Unknown')
        media_type = item.get('media_type', 'unknown')
        item_id = item.get('id')
        genres = item.get('genre_ids', [])
        print(f"      {i+1}. {title} ({media_type}) - ID: {item_id} - Genres: {genres}")
    
    # Find a movie with adventure genre (ID 12) to track
    target_movie = None
    target_index = None
    
    for i, item in enumerate(initial_items):
        if (item.get('media_type') == 'movie' and 
            item.get('genre_ids') and 
            12 in item.get('genre_ids', [])):  # 12 = Adventure genre
            target_movie = item
            target_index = i
            break
    
    if not target_movie:
        print("   ⚠️  No adventure movie found in initial results")
        print("   🔍 Looking for any movie with genres to track...")
        # Find any movie with genres to track
        for i, item in enumerate(initial_items):
            if (item.get('media_type') == 'movie' and 
                item.get('genre_ids')):
                target_movie = item
                target_index = i
                print(f"   📍 Found trackable movie: {item.get('title')} with genres {item.get('genre_ids')}")
                break
    
    if not target_movie:
        print("   ❌ No trackable movie found - cannot test consistency")
        return False
        
    target_title = target_movie.get('title', 'Unknown')
    target_id = target_movie.get('id')
    target_genres = target_movie.get('genre_ids', [])
    
    print(f"   🎯 TRACKING: '{target_title}' (ID: {target_id}) at position {target_index + 1}")
    print(f"   🏷️  Movie genres: {target_genres}")
    print(f"   🔍 Has adventure genre (12): {12 in target_genres}")
    
    # Step 2: Add genre filter - should preserve the tracked movie if it matches
    print(f"\n🎭 STEP 2: Add genre filter")
    
    # Use one of the genres from our tracked movie
    test_genre = target_genres[0] if target_genres else 12  # Use adventure if no genres
    print(f"   🎯 Testing with genre ID: {test_genre}")
    
    filtered_results = tmdb_service._get_mixed_content(
        category="popular", 
        page=1,
        with_genres=str(test_genre),
        primary_release_date_gte="2024-01-01",
        primary_release_date_lte="2025-12-31",
        first_air_date_gte="2024-01-01",
        first_air_date_lte="2025-12-31"
    )
    
    filtered_items = filtered_results.get('results', [])
    print(f"   📊 Filtered results: {len(filtered_items)} items")
    
    # Check if our tracked movie is still present
    found_target = False
    new_position = None
    
    for i, item in enumerate(filtered_items):
        if item.get('id') == target_id:
            found_target = True
            new_position = i
            break
    
    print("   📋 First 5 filtered items:")
    for i, item in enumerate(filtered_items[:5]):
        title = item.get('title') or item.get('name', 'Unknown')
        media_type = item.get('media_type', 'unknown')
        item_id = item.get('id')
        match_indicator = "🎯" if item_id == target_id else "  "
        print(f"      {match_indicator}{i+1}. {title} ({media_type}) - ID: {item_id}")
    
    # Step 3: Analyze results
    print(f"\n🔍 ANALYSIS:")
    
    if found_target:
        print(f"   ✅ GOOD: Tracked movie '{target_title}' is still present")
        print(f"   📍 Original position: {target_index + 1}")
        print(f"   📍 New position: {new_position + 1}")
        
        if new_position <= target_index + 5:  # Allow some reasonable reordering
            print(f"   ✅ GOOD: Position change is reasonable (within 5 positions)")
        else:
            print(f"   ⚠️  CONCERN: Large position change ({abs(new_position - target_index)} positions)")
            
    else:
        if test_genre in target_genres:
            print(f"   ❌ BUG CONFIRMED: Movie '{target_title}' disappeared despite matching genre {test_genre}")
            print(f"   🐛 This confirms the user's reported issue!")
            return False
        else:
            print(f"   ✅ EXPECTED: Movie doesn't match genre {test_genre}, correctly filtered out")
    
    # Step 4: Test sorting consistency
    print(f"\n📊 SORTING CONSISTENCY CHECK:")
    
    # Extract popularity scores and check if they're in descending order
    initial_popularities = [item.get('popularity', 0) for item in initial_items[:10]]
    filtered_popularities = [item.get('popularity', 0) for item in filtered_items[:10]]
    
    print(f"   📈 Initial popularities (first 10): {[round(p, 1) for p in initial_popularities]}")
    print(f"   📈 Filtered popularities (first 10): {[round(p, 1) for p in filtered_popularities]}")
    
    # Check if sorting is consistent (descending popularity)
    initial_sorted = all(initial_popularities[i] >= initial_popularities[i+1] 
                        for i in range(len(initial_popularities)-1))
    filtered_sorted = all(filtered_popularities[i] >= filtered_popularities[i+1] 
                         for i in range(len(filtered_popularities)-1))
    
    if initial_sorted and filtered_sorted:
        print(f"   ✅ GOOD: Both result sets are properly sorted by popularity (desc)")
    else:
        print(f"   ❌ ISSUE: Sorting inconsistency detected!")
        print(f"      Initial sorted: {initial_sorted}")
        print(f"      Filtered sorted: {filtered_sorted}")
        return False
    
    # Step 5: Test the exact user scenario with adventure genre
    print(f"\n🏔️  STEP 5: Test exact user scenario (adventure genre)")
    
    adventure_results = tmdb_service._get_mixed_content(
        category="popular",
        page=1,
        with_genres="12",  # Adventure genre
        primary_release_date_gte="2024-01-01",
        primary_release_date_lte="2025-12-31", 
        first_air_date_gte="2024-01-01",
        first_air_date_lte="2025-12-31"
    )
    
    adventure_items = adventure_results.get('results', [])
    print(f"   📊 Adventure filtered results: {len(adventure_items)} items")
    
    # Check if any movie from initial results with adventure genre is present
    initial_adventure_movies = [
        item for item in initial_items 
        if item.get('media_type') == 'movie' and 12 in item.get('genre_ids', [])
    ]
    
    print(f"   🎯 Initial adventure movies: {len(initial_adventure_movies)}")
    
    if initial_adventure_movies:
        for movie in initial_adventure_movies[:3]:  # Check first 3
            movie_id = movie.get('id')
            movie_title = movie.get('title')
            found_in_filtered = any(item.get('id') == movie_id for item in adventure_items)
            
            if found_in_filtered:
                print(f"   ✅ GOOD: '{movie_title}' preserved in adventure filter")
            else:
                print(f"   ❌ BUG: '{movie_title}' disappeared despite being adventure movie!")
                return False
    else:
        print(f"   ℹ️  No adventure movies in initial results to track")
    
    print(f"\n🎉 FILTER CONSISTENCY TEST: PASSED")
    print(f"✅ Movies are properly preserved when adding matching genre filters")
    print(f"✅ Sorting remains consistent across filter applications")
    print(f"✅ The reported bug does not appear to be present")
    
    return True

def test_specific_parameters():
    """Test with the exact TMDB API parameters that might be causing issues"""
    
    print("\n" + "=" * 70)
    print("🔬 DETAILED PARAMETER ANALYSIS")
    print("=" * 70)
    
    tmdb_service = TMDBService()
    
    # Test different sorting parameters to see if they affect results
    sort_methods = ['popularity.desc', 'vote_average.desc', 'release_date.desc']
    
    for sort_method in sort_methods:
        print(f"\n📊 Testing sort method: {sort_method}")
        
        try:
            results = tmdb_service.discover_movies(
                page=1,
                sort_by=sort_method,
                primary_release_date_gte="2024-01-01",
                primary_release_date_lte="2025-12-31"
            )
            
            items = results.get('results', [])[:5]
            print(f"   📈 Results: {len(items)} items")
            
            for i, item in enumerate(items):
                title = item.get('title', 'Unknown')
                popularity = item.get('popularity', 0)
                rating = item.get('vote_average', 0)
                print(f"      {i+1}. {title} - Pop: {popularity:.1f}, Rating: {rating:.1f}")
                
        except Exception as e:
            print(f"   ❌ Error with {sort_method}: {e}")
    
    return True

if __name__ == "__main__":
    print("🚀 Starting Filter Consistency Analysis")
    
    try:
        bug_test_passed = test_filter_consistency_bug()
        param_test_passed = test_specific_parameters()
        
        if bug_test_passed and param_test_passed:
            print("\n🎯 CONCLUSION: Filter consistency appears to be working correctly")
            print("🤔 The reported bug may be in a different area or require specific conditions")
            print("💡 Recommendations:")
            print("   1. Check for JavaScript interference in the web interface")
            print("   2. Verify HTMX form submission parameters")
            print("   3. Test with specific movie/genre combinations")
            print("   4. Add comprehensive logging to track the exact issue")
            sys.exit(0)
        else:
            print("\n🚨 CONCLUSION: Filter consistency issues detected!")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)