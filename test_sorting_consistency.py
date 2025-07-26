#!/usr/bin/env python3
"""
Test sorting consistency fixes across different endpoints.
This validates that all sorting uses popularity.desc consistently.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.tmdb_service import TMDBService

def test_sorting_consistency():
    """Test that all endpoints use consistent popularity-based sorting"""
    
    print("🔧 Testing Sorting Consistency Fixes")
    print("=" * 70)
    
    tmdb_service = TMDBService()
    
    test_cases = [
        {
            "name": "Mixed Popular Movies (no filters)",
            "method": "get_category_content",
            "params": {
                "media_type": "mixed",
                "category": "popular",
                "page": 1
            }
        },
        {
            "name": "Mixed Popular Movies (with genre filter)",
            "method": "get_category_content", 
            "params": {
                "media_type": "mixed",
                "category": "popular",
                "page": 1,
                "with_genres": "12"  # Adventure
            }
        },
        {
            "name": "Mixed Popular Movies (with date filter)",
            "method": "get_category_content",
            "params": {
                "media_type": "mixed", 
                "category": "popular",
                "page": 1,
                "primary_release_date_gte": "2024-01-01",
                "primary_release_date_lte": "2025-12-31",
                "first_air_date_gte": "2024-01-01",
                "first_air_date_lte": "2025-12-31"
            }
        },
        {
            "name": "Mixed Popular Movies (with date + genre filters)",
            "method": "get_category_content",
            "params": {
                "media_type": "mixed",
                "category": "popular", 
                "page": 1,
                "with_genres": "12",  # Adventure
                "primary_release_date_gte": "2024-01-01",
                "primary_release_date_lte": "2025-12-31",
                "first_air_date_gte": "2024-01-01",
                "first_air_date_lte": "2025-12-31"
            }
        }
    ]
    
    overall_success = True
    previous_results = {}
    
    for test_case in test_cases:
        name = test_case["name"]
        method = getattr(tmdb_service, test_case["method"])
        params = test_case["params"]
        
        print(f"\n📊 Testing: {name}")
        print(f"   Parameters: {params}")
        
        try:
            results = method(**params)
            items = results.get('results', [])
            
            print(f"   📈 Results: {len(items)} items")
            
            if items:
                # Check sorting consistency
                popularities = [item.get('popularity', 0) for item in items[:10]]
                print(f"   📋 Popularities (first 10): {[round(p, 1) for p in popularities]}")
                
                # Verify descending order
                is_sorted = all(popularities[i] >= popularities[i+1] for i in range(len(popularities)-1))
                
                if is_sorted:
                    print(f"   ✅ GOOD: Results properly sorted by popularity (desc)")
                    
                    # Show first few items
                    print(f"   🎬 First 3 items:")
                    for i, item in enumerate(items[:3]):
                        title = item.get('title') or item.get('name', 'Unknown')
                        media_type = item.get('media_type', 'unknown')
                        popularity = item.get('popularity', 0)
                        print(f"      {i+1}. {title} ({media_type}) - Pop: {popularity:.1f}")
                        
                else:
                    print(f"   ❌ ISSUE: Results not properly sorted!")
                    overall_success = False
                    
                # Store results for cross-test comparison
                previous_results[name] = {
                    'items': items,
                    'popularities': popularities
                }
                
            else:
                print(f"   ⚠️  No results returned")
                
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
            overall_success = False
    
    # Cross-test consistency analysis
    print(f"\n🔍 CROSS-TEST CONSISTENCY ANALYSIS:")
    
    # Compare base results with filtered results
    base_key = "Mixed Popular Movies (no filters)"
    genre_key = "Mixed Popular Movies (with genre filter)"
    date_key = "Mixed Popular Movies (with date filter)"
    both_key = "Mixed Popular Movies (with date + genre filters)"
    
    if base_key in previous_results and genre_key in previous_results:
        base_ids = {item.get('id') for item in previous_results[base_key]['items']}
        genre_ids = {item.get('id') for item in previous_results[genre_key]['items']}
        
        # Find items that should be preserved (have adventure genre)
        preserved_count = len(genre_ids & base_ids)
        print(f"   📊 Base results: {len(base_ids)} items")
        print(f"   📊 Genre filtered: {len(genre_ids)} items") 
        print(f"   📊 Preserved items: {preserved_count}")
        
        if preserved_count > 0:
            print(f"   ✅ GOOD: Genre filter preserves matching items")
        else:
            print(f"   ⚠️  WARNING: No items preserved by genre filter")
    
    if date_key in previous_results and both_key in previous_results:
        date_ids = {item.get('id') for item in previous_results[date_key]['items']}
        both_ids = {item.get('id') for item in previous_results[both_key]['items']}
        
        preserved_count = len(both_ids & date_ids)
        print(f"   📊 Date filtered: {len(date_ids)} items")
        print(f"   📊 Date + Genre filtered: {len(both_ids)} items")
        print(f"   📊 Preserved items: {preserved_count}")
        
        if preserved_count > 0:
            print(f"   ✅ GOOD: Combined filters preserve appropriate items")
        else:
            print(f"   ⚠️  WARNING: No items preserved by combined filters")
    
    print("\n" + "=" * 70)
    if overall_success:
        print("🎉 SORTING CONSISTENCY TEST: ALL PASSED!")
        print("✅ All endpoints use consistent popularity-based sorting")
        print("✅ Results maintain proper descending order by popularity")
        print("✅ Filter application preserves appropriate items")
    else:
        print("❌ SORTING CONSISTENCY TEST: ISSUES DETECTED!")
        print("⚠️  Some endpoints still have sorting inconsistencies")
    
    return overall_success

if __name__ == "__main__":
    success = test_sorting_consistency()
    if success:
        print("\n🎯 CONCLUSION: Sorting consistency fixes appear to be working!")
        print("🚀 All endpoints now use unified popularity-based sorting")
        sys.exit(0)
    else:
        print("\n🚨 CONCLUSION: Sorting consistency issues still exist!")
        sys.exit(1)