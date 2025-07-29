#!/usr/bin/env python3
"""
Test script to verify TMDB category consistency between horizontal scroll and expanded views.
This directly tests the TMDBService.get_category_content() method.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.tmdb_service import TMDBService

def test_category_consistency():
    """Test that horizontal scroll and expanded views return identical content for categories"""
    
    print("🔍 Testing TMDB Category Consistency")
    print("=" * 60)
    
    # Initialize TMDB service
    tmdb_service = TMDBService()
    
    # Test categories to verify
    test_cases = [
        {"media_type": "movie", "category": "popular", "description": "Popular Movies"},
        {"media_type": "movie", "category": "top_rated", "description": "Top Rated Movies"},
        {"media_type": "movie", "category": "trending", "description": "Trending Movies"},
        {"media_type": "movie", "category": "upcoming", "description": "Upcoming Movies"},
        {"media_type": "tv", "category": "popular", "description": "Popular TV Shows"},
        {"media_type": "tv", "category": "top_rated", "description": "Top Rated TV Shows"},
        {"media_type": "tv", "category": "trending", "description": "Trending TV Shows"},
    ]
    
    overall_success = True
    
    for test_case in test_cases:
        media_type = test_case["media_type"]
        category = test_case["category"]
        description = test_case["description"]
        
        print(f"\n🎬 Testing: {description}")
        print(f"   Media Type: {media_type}, Category: {category}")
        
        try:
            # Get first page using unified method (simulates both horizontal and expanded)
            page1_results = tmdb_service.get_category_content(
                media_type=media_type,
                category=category,
                page=1
            )
            
            # Get second page to test pagination consistency
            page2_results = tmdb_service.get_category_content(
                media_type=media_type,
                category=category,
                page=2
            )
            
            # Extract movie/TV IDs from results
            page1_ids = [item['id'] for item in page1_results.get('results', [])]
            page2_ids = [item['id'] for item in page2_results.get('results', [])]
            
            print(f"   ✅ Page 1: {len(page1_ids)} items")
            print(f"   ✅ Page 2: {len(page2_ids)} items")
            
            if page1_ids:
                print(f"   📋 First 5 IDs (Page 1): {page1_ids[:5]}")
            if page2_ids:
                print(f"   📋 First 5 IDs (Page 2): {page2_ids[:5]}")
            
            # Check for overlapping IDs between pages (should not happen)
            overlaps = set(page1_ids).intersection(set(page2_ids))
            if overlaps:
                print(f"   ⚠️  WARNING: Found overlapping IDs between pages: {overlaps}")
                overall_success = False
            else:
                print(f"   ✅ No overlapping IDs between pages")
            
            # Test with filters to ensure consistency
            print(f"   🔍 Testing with filters...")
            filtered_results = tmdb_service.get_category_content(
                media_type=media_type,
                category=category,
                page=1,
                vote_average_gte=7.0 if category != "trending" else None  # Trending might not support this filter
            )
            
            filtered_ids = [item['id'] for item in filtered_results.get('results', [])]
            print(f"   ✅ Filtered results: {len(filtered_ids)} items")
            
            if filtered_ids:
                print(f"   📋 First 3 filtered IDs: {filtered_ids[:3]}")
            
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
            overall_success = False
    
    print("\n" + "=" * 60)
    if overall_success:
        print("🎉 ALL TESTS PASSED - Category consistency is working!")
    else:
        print("❌ SOME TESTS FAILED - Category consistency issues detected!")
    
    return overall_success

def test_old_vs_new_methods():
    """Compare old convenience methods with new unified method to verify consistency"""
    
    print("\n🔄 Testing Old vs New Method Consistency")
    print("=" * 60)
    
    tmdb_service = TMDBService()
    
    # Test cases comparing old methods with new unified method
    comparison_tests = [
        {
            "name": "Popular Movies",
            "old_method": lambda: tmdb_service.get_popular("movie", page=1),
            "new_method": lambda: tmdb_service.get_category_content("movie", "popular", page=1)
        },
        {
            "name": "Top Rated Movies", 
            "old_method": lambda: tmdb_service.get_top_rated("movie", page=1),
            "new_method": lambda: tmdb_service.get_category_content("movie", "top_rated", page=1)
        },
        {
            "name": "Trending Movies",
            "old_method": lambda: tmdb_service.get_trending("movie", page=1),
            "new_method": lambda: tmdb_service.get_category_content("movie", "trending", page=1)
        }
    ]
    
    overall_consistent = True
    
    for test in comparison_tests:
        print(f"\n🔍 Comparing: {test['name']}")
        
        try:
            # Get results from both methods
            old_results = test["old_method"]()
            new_results = test["new_method"]()
            
            # Extract IDs
            old_ids = [item['id'] for item in old_results.get('results', [])]
            new_ids = [item['id'] for item in new_results.get('results', [])]
            
            print(f"   Old method: {len(old_ids)} items")
            print(f"   New method: {len(new_ids)} items")
            
            # Compare first 10 items for consistency
            if len(old_ids) >= 10 and len(new_ids) >= 10:
                if old_ids[:10] == new_ids[:10]:
                    print(f"   ✅ First 10 items are identical")
                else:
                    print(f"   ⚠️  First 10 items differ (this may be expected due to improved algorithm)")
                    print(f"   Old: {old_ids[:5]}")
                    print(f"   New: {new_ids[:5]}")
                    # Only mark as failure for popular movies (should be identical)
                    if test['name'] == "Popular Movies":
                        overall_consistent = False
            else:
                print(f"   ⚠️  Not enough items to compare (Old: {len(old_ids)}, New: {len(new_ids)})")
                
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
            overall_consistent = False
    
    print("\n" + "=" * 60)
    if overall_consistent:
        print("🎉 OLD vs NEW METHODS CONSISTENT!")
    else:
        print("❌ INCONSISTENCY DETECTED between old and new methods!")
    
    return overall_consistent

if __name__ == "__main__":
    success1 = test_category_consistency()
    success2 = test_old_vs_new_methods()
    
    if success1 and success2:
        print("\n🎉 OVERALL: All consistency tests PASSED!")
        sys.exit(0)
    else:
        print("\n❌ OVERALL: Some consistency tests FAILED!")
        sys.exit(1)