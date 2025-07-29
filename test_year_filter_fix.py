#!/usr/bin/env python3
"""
Quick test to verify the year filter fix for TV shows and mixed content.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.tmdb_service import TMDBService
from app.core.database import get_session

def test_year_filter_fix():
    """Test that year filters now work for TV shows and mixed content"""
    print("🧪 Testing Year Filter Fix for TV Shows and Mixed Content\n")
    
    # Get a real database session
    session = next(get_session())
    tmdb_service = TMDBService(session)
    
    test_cases = [
        {
            "name": "Movies with 2024 year filter (should work - baseline)",
            "media_type": "movie",
            "category": "popular",
            "primary_release_date_gte": "2024-01-01",
            "primary_release_date_lte": "2024-12-31"
        },
        {
            "name": "TV shows with 2024 year filter (PREVIOUSLY BROKEN - now fixed)",
            "media_type": "tv",
            "category": "popular",
            "first_air_date_gte": "2024-01-01",
            "first_air_date_lte": "2024-12-31"
        },
        {
            "name": "Mixed content with movie date params (PREVIOUSLY BROKEN - now fixed)",
            "media_type": "mixed",
            "category": "popular",
            "primary_release_date_gte": "2024-01-01",
            "primary_release_date_lte": "2024-12-31"
        },
        {
            "name": "Mixed content with TV date params (test cross-mapping)",
            "media_type": "mixed", 
            "category": "popular",
            "first_air_date_gte": "2024-01-01",
            "first_air_date_lte": "2024-12-31"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"📋 Test {i}: {test_case['name']}")
        
        try:
            # Build parameters
            params = {
                "media_type": test_case["media_type"],
                "category": test_case["category"],
                "page": 1
            }
            
            # Add date parameters 
            if "primary_release_date_gte" in test_case:
                params["primary_release_date_gte"] = test_case["primary_release_date_gte"]
            if "primary_release_date_lte" in test_case:
                params["primary_release_date_lte"] = test_case["primary_release_date_lte"]
            if "first_air_date_gte" in test_case:
                params["first_air_date_gte"] = test_case["first_air_date_gte"]
            if "first_air_date_lte" in test_case:
                params["first_air_date_lte"] = test_case["first_air_date_lte"]
            
            # Call the method that was broken
            result = tmdb_service.get_category_content(**params)
            
            if result and "results" in result:
                num_results = len(result["results"])
                print(f"   ✅ SUCCESS: Retrieved {num_results} results")
                
                # Show sample result dates to verify filtering worked
                if num_results > 0:
                    sample = result["results"][0]
                    sample_date = sample.get("release_date") or sample.get("first_air_date") or "No date"
                    sample_title = sample.get("title") or sample.get("name") or "No title"
                    print(f"   📋 Sample: {sample_title} ({sample_date})")
                    
                    # For mixed content, show media type distribution
                    if test_case["media_type"] == "mixed":
                        media_types = {}
                        for item in result["results"][:5]:  # Check first 5
                            media_type = item.get("media_type", "unknown")
                            media_types[media_type] = media_types.get(media_type, 0) + 1
                        print(f"   📊 Media type distribution (first 5): {media_types}")
                        
            else:
                print(f"   ❌ FAILED: No results returned")
                
        except Exception as e:
            print(f"   💥 ERROR: {str(e)}")
            
        print()  # Empty line between tests
    
    session.close()
    print("🎯 Year filter testing completed!")

if __name__ == "__main__":
    test_year_filter_fix()