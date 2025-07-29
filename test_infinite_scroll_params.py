#!/usr/bin/env python3
"""
Test infinite scroll parameter mapping with actual endpoint call simulation.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.tmdb_service import TMDBService
from app.core.database import get_session

def simulate_infinite_scroll_calls():
    """Simulate the infinite scroll calls that would happen from the frontend"""
    print("🚀 Simulating Infinite Scroll Parameter Mapping\n")
    
    session = next(get_session())
    tmdb_service = TMDBService(session)
    
    # These simulate the exact calls that would be made by the infinite scroll endpoint
    test_scenarios = [
        {
            "name": "Movies - Popular with year 2024 filter (page 2)",
            "params": {
                "media_type": "movie",
                "category": "popular", 
                "page": 2,
                "primary_release_date_gte": "2024-01-01",
                "primary_release_date_lte": "2024-12-31"
            }
        },
        {
            "name": "TV Shows - Popular with year 2024 filter (page 2) - THE CRITICAL TEST",
            "params": {
                "media_type": "tv",
                "category": "popular",
                "page": 2,
                "first_air_date_gte": "2024-01-01", 
                "first_air_date_lte": "2024-12-31"
            }
        },
        {
            "name": "Mixed Content - Popular with year 2024 filter (page 2) - THE CRITICAL TEST",
            "params": {
                "media_type": "mixed",
                "category": "popular",
                "page": 2,
                "primary_release_date_gte": "2024-01-01",
                "primary_release_date_lte": "2024-12-31"
            }
        },
        {
            "name": "Mixed Content - Trending with combined filters",
            "params": {
                "media_type": "mixed",
                "category": "trending", 
                "page": 1,
                "primary_release_date_gte": "2023-01-01",
                "primary_release_date_lte": "2024-12-31",
                "with_genres": "28,12",  # Action, Adventure
                "vote_average_gte": 6.0
            }
        }
    ]
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"📋 Test {i}: {scenario['name']}")
        print(f"   🔧 Parameters: {scenario['params']}")
        
        try:
            # This is the exact call made by the infinite scroll endpoint
            result = tmdb_service.get_category_content(**scenario['params'])
            
            if result and "results" in result:
                num_results = len(result["results"])
                total_results = result.get("total_results", 0)
                total_pages = result.get("total_pages", 0)
                
                print(f"   ✅ SUCCESS: Got {num_results} results (Total: {total_results}, Pages: {total_pages})")
                
                # Show sample to verify filter is working
                if num_results > 0:
                    sample = result["results"][0]
                    sample_date = sample.get("release_date") or sample.get("first_air_date") or "No date"
                    sample_title = sample.get("title") or sample.get("name") or "No title"
                    sample_type = sample.get("media_type", "unknown")
                    print(f"   📋 Sample result: {sample_title} ({sample_date}) [{sample_type}]")
                    
                    # For mixed content, show distribution
                    if scenario['params']['media_type'] == 'mixed':
                        media_types = {}
                        for item in result["results"][:10]:
                            media_type = item.get("media_type", "unknown") 
                            media_types[media_type] = media_types.get(media_type, 0) + 1
                        print(f"   📊 Media type distribution: {media_types}")
                
                # Validate date filtering actually worked
                if "primary_release_date_gte" in scenario['params'] or "first_air_date_gte" in scenario['params']:
                    date_filter_working = False
                    for item in result["results"][:3]:  # Check first 3 items
                        item_date = item.get("release_date") or item.get("first_air_date")
                        if item_date and "2024" in item_date or "2023" in item_date:
                            date_filter_working = True
                            break
                    
                    if date_filter_working:
                        print(f"   🎯 Date filter appears to be working correctly")
                    else:
                        print(f"   ⚠️  Date filter may not be working (check manually)")
                        
            else:
                print(f"   ❌ FAILED: No results returned")
                
        except Exception as e:
            print(f"   💥 ERROR: {str(e)}")
            
        print()  # Empty line between tests
    
    session.close()
    print("🎯 Infinite scroll parameter testing completed!")

if __name__ == "__main__":
    simulate_infinite_scroll_calls()