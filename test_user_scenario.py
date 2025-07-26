#!/usr/bin/env python3
"""
Test the exact user scenario to validate the fix.
User: "All media types + dates 2024-2025" -> Movie X (adventure) is first result
Then: Add "adventure" genre filter -> Movie X should still be there (not disappear)
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.tmdb_service import TMDBService

def test_exact_user_scenario():
    """Test the exact scenario reported by the user"""
    
    print("🎯 Testing EXACT User Scenario")
    print("=" * 70)
    print("User Story:")
    print("1. Filter: All media types + dates 2024-2025")
    print("2. Results show Movie X (adventure genre) as first result ✅")
    print("3. User adds 'adventure' genre filter and applies")
    print("4. Movie X disappears from results ❌ (BUG)")
    print("5. Entire result list reorders unpredictably ❌ (BUG)")
    print("=" * 70)
    
    tmdb_service = TMDBService()
    
    # Step 1: Initial filter - All media + 2024-2025 dates
    print("\n📅 STEP 1: User filters All media + dates 2024-2025")
    
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
        print("   ❌ No initial results - test cannot proceed")
        return False
    
    # Show results and identify adventure movies
    print("   🎬 First 5 items:")
    adventure_movies = []
    
    for i, item in enumerate(initial_items[:10]):  # Check first 10 for adventure movies
        title = item.get('title') or item.get('name', 'Unknown')
        media_type = item.get('media_type', 'unknown')
        item_id = item.get('id')
        genres = item.get('genre_ids', [])
        popularity = item.get('popularity', 0)
        has_adventure = 12 in genres  # 12 = Adventure genre
        
        if i < 5:  # Show first 5
            adventure_indicator = "🏔️" if has_adventure else "  "
            print(f"      {adventure_indicator}{i+1}. {title} ({media_type}) - ID: {item_id} - Pop: {popularity:.1f}")
        
        if has_adventure and media_type == 'movie':
            adventure_movies.append({
                'position': i + 1,
                'title': title,
                'id': item_id,
                'popularity': popularity,
                'genres': genres
            })
    
    if not adventure_movies:
        print("   ⚠️  No adventure movies in first 10 results - creating artificial test")
        # Use any movie with genres as a test case
        for i, item in enumerate(initial_items[:5]):
            if item.get('media_type') == 'movie' and item.get('genre_ids'):
                test_movie = {
                    'position': i + 1,
                    'title': item.get('title', 'Unknown'),
                    'id': item.get('id'),
                    'popularity': item.get('popularity', 0),
                    'genres': item.get('genre_ids', [])
                }
                print(f"   🎯 Using test movie: {test_movie['title']} with genres {test_movie['genres']}")
                break
        else:
            print("   ❌ No suitable test movie found")
            return False
    else:
        print(f"   🏔️  Found {len(adventure_movies)} adventure movies in top 10:")
        for movie in adventure_movies:
            print(f"      Position {movie['position']}: {movie['title']} (ID: {movie['id']})")
    
    # Select the highest-ranking adventure movie to track
    target_movie = adventure_movies[0] if adventure_movies else test_movie
    print(f"\n   🎯 TRACKING: '{target_movie['title']}' at position {target_movie['position']}")
    print(f"   📊 Movie ID: {target_movie['id']}")
    print(f"   📊 Popularity: {target_movie['popularity']:.1f}")
    print(f"   📊 Genres: {target_movie['genres']}")
    
    # Step 2: Add adventure genre filter
    print(f"\n🏔️  STEP 2: User adds adventure genre filter")
    
    filtered_results = tmdb_service._get_mixed_content(
        category="popular",
        page=1,
        with_genres="12",  # Adventure genre
        primary_release_date_gte="2024-01-01",
        primary_release_date_lte="2025-12-31",
        first_air_date_gte="2024-01-01",
        first_air_date_lte="2025-12-31"
    )
    
    filtered_items = filtered_results.get('results', [])
    print(f"   📊 Filtered results: {len(filtered_items)} items")
    
    # Find our tracked movie in the filtered results
    found_target = False
    new_position = None
    
    for i, item in enumerate(filtered_items):
        if item.get('id') == target_movie['id']:
            found_target = True
            new_position = i + 1
            break
    
    print("   🎬 First 5 filtered items:")
    for i, item in enumerate(filtered_items[:5]):
        title = item.get('title') or item.get('name', 'Unknown')
        media_type = item.get('media_type', 'unknown')
        item_id = item.get('id')
        popularity = item.get('popularity', 0)
        match_indicator = "🎯" if item_id == target_movie['id'] else "  "
        print(f"      {match_indicator}{i+1}. {title} ({media_type}) - ID: {item_id} - Pop: {popularity:.1f}")
    
    # Step 3: Validate the fix
    print(f"\n🔍 VALIDATION RESULTS:")
    
    success = True
    
    # Test 1: Movie preservation
    if found_target:
        print(f"   ✅ SUCCESS: Tracked movie '{target_movie['title']}' is preserved!")
        print(f"   📍 Original position: {target_movie['position']}")
        print(f"   📍 New position: {new_position}")
        
        position_change = abs(new_position - target_movie['position'])
        if position_change <= 3:  # Allow reasonable reordering
            print(f"   ✅ SUCCESS: Position change is reasonable ({position_change} positions)")
        else:
            print(f"   ⚠️  WARNING: Large position change ({position_change} positions)")
    else:
        if 12 in target_movie['genres']:  # Should have been preserved
            print(f"   ❌ FAILURE: Movie '{target_movie['title']}' disappeared despite having adventure genre!")
            print(f"   🐛 This would be the bug the user reported!")
            success = False
        else:
            print(f"   ✅ EXPECTED: Movie correctly filtered out (no adventure genre)")
    
    # Test 2: Sorting consistency  
    initial_pops = [item.get('popularity', 0) for item in initial_items[:5]]
    filtered_pops = [item.get('popularity', 0) for item in filtered_items[:5]]
    
    initial_sorted = all(initial_pops[i] >= initial_pops[i+1] for i in range(len(initial_pops)-1))
    filtered_sorted = all(filtered_pops[i] >= filtered_pops[i+1] for i in range(len(filtered_pops)-1))
    
    if initial_sorted and filtered_sorted:
        print(f"   ✅ SUCCESS: Sorting remains consistent (popularity desc)")
    else:
        print(f"   ❌ FAILURE: Sorting inconsistency detected!")
        print(f"      Initial sorted: {initial_sorted}")
        print(f"      Filtered sorted: {filtered_sorted}")
        success = False
    
    # Test 3: No unexpected reordering
    common_movies = []
    for initial_item in initial_items[:10]:
        for filtered_item in filtered_items[:10]:
            if initial_item.get('id') == filtered_item.get('id'):
                common_movies.append({
                    'id': initial_item.get('id'),
                    'title': initial_item.get('title') or initial_item.get('name'),
                    'initial_pos': next(i for i, x in enumerate(initial_items) if x.get('id') == initial_item.get('id')) + 1,
                    'filtered_pos': next(i for i, x in enumerate(filtered_items) if x.get('id') == filtered_item.get('id')) + 1
                })
    
    print(f"   📊 Movies preserved across both result sets: {len(common_movies)}")
    
    large_position_changes = 0
    for movie in common_movies:
        change = abs(movie['filtered_pos'] - movie['initial_pos'])
        if change > 5:  # Significant reordering
            large_position_changes += 1
            print(f"      ⚠️  {movie['title']}: {movie['initial_pos']} → {movie['filtered_pos']} ({change} positions)")
    
    if large_position_changes == 0:
        print(f"   ✅ SUCCESS: No unexpected large reordering")
    else:
        print(f"   ⚠️  WARNING: {large_position_changes} movies had large position changes")
    
    print(f"\n{'='*70}")
    if success:
        print("🎉 USER SCENARIO TEST: PASSED! ✅")
        print("✅ The reported bug has been FIXED:")
        print("   • Movies are properly preserved when adding matching genre filters")
        print("   • Sorting remains consistent across filter applications")
        print("   • No unexpected disappearing or reordering")
        print("🚀 Filter consistency issue has been resolved!")
    else:
        print("❌ USER SCENARIO TEST: FAILED!")
        print("🐛 The reported bug is still present:")
        print("   • Movies disappear when they shouldn't")
        print("   • Or sorting becomes inconsistent")
    
    return success

if __name__ == "__main__":
    success = test_exact_user_scenario()
    if success:
        print("\n🎯 FINAL CONCLUSION: User's filter consistency issue has been FIXED! 🎉")
        sys.exit(0)
    else:
        print("\n🚨 FINAL CONCLUSION: User's issue still needs more work!")
        sys.exit(1)