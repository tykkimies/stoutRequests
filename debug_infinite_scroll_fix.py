#!/usr/bin/env python3
"""
Debug and fix infinite scroll pagination issues.

This script tests the specific issues mentioned:
1. Infinite scroll only loads one additional page, then stops
2. Mixed content type issues with request buttons
3. Query parameter persistence issues
"""

import asyncio
import sys
import os
sys.path.append('/opt/stoutRequests')

from app.services.tmdb_service import TMDBService
from sqlmodel import Session, create_engine, SQLModel
from app.core.database import get_engine

async def test_infinite_scroll_pagination():
    """Test pagination behavior for different media types and scenarios"""
    
    print("🔍 Testing infinite scroll pagination issues...")
    
    # Get database session
    engine = get_engine()
    
    with Session(engine) as session:
        tmdb_service = TMDBService(session)
        
        # Test scenarios that were mentioned as problematic
        test_scenarios = [
            {
                "name": "Mixed Content - Popular",
                "media_type": "mixed",
                "category": "popular",
                "expected_behavior": "Should continue loading pages beyond page 2"
            },
            {
                "name": "Mixed Content - Trending",
                "media_type": "mixed", 
                "category": "trending",
                "expected_behavior": "Should continue loading pages beyond page 2"
            },
            {
                "name": "Movie Only - Popular",
                "media_type": "movie",
                "category": "popular", 
                "expected_behavior": "Should work as baseline"
            },
            {
                "name": "TV Only - Popular",
                "media_type": "tv",
                "category": "popular",
                "expected_behavior": "Should work as baseline"
            }
        ]
        
        for scenario in test_scenarios:
            print(f"\n📋 Testing: {scenario['name']}")
            print(f"   Expected: {scenario['expected_behavior']}")
            
            # Test multiple pages to see where it breaks
            for page in range(1, 5):  # Test pages 1-4
                try:
                    print(f"   📄 Testing page {page}...")
                    
                    results = tmdb_service.get_category_content(
                        media_type=scenario["media_type"],
                        category=scenario["category"],
                        page=page
                    )
                    
                    results_count = len(results.get('results', []))
                    total_pages = results.get('total_pages', 0)
                    total_results = results.get('total_results', 0)
                    
                    print(f"      ✅ Page {page}: {results_count} items, {total_pages} total pages, {total_results} total results")
                    
                    # Check for media_type on each item
                    if scenario["media_type"] == "mixed":
                        media_types = [item.get('media_type') for item in results.get('results', [])]
                        movie_count = media_types.count('movie')
                        tv_count = media_types.count('tv') 
                        none_count = media_types.count(None)
                        
                        print(f"      📊 Mixed content breakdown: {movie_count} movies, {tv_count} TV shows, {none_count} without media_type")
                        
                        if none_count > 0:
                            print(f"      ⚠️  WARNING: {none_count} items missing media_type!")
                    
                    # Check if pagination would continue
                    if page < total_pages and results_count == 0:
                        print(f"      ❌ PAGINATION BUG: Page {page} returned 0 results but total_pages={total_pages}")
                        break
                    elif page >= total_pages and results_count > 0:
                        print(f"      ⚠️  Unexpected: Page {page} >= total_pages ({total_pages}) but got {results_count} results")
                    elif page < total_pages and results_count > 0:
                        print(f"      ✅ Page {page} looks good - has results and more pages available")
                    elif page >= total_pages:
                        print(f"      ✅ Reached end of pagination normally")
                        break
                        
                except Exception as e:
                    print(f"      ❌ ERROR on page {page}: {e}")
                    break

def test_query_param_building():
    """Test the build_discover_query_params function"""
    print("\n🔧 Testing query parameter building...")
    
    # Import the function
    from app.main import build_discover_query_params
    
    test_cases = [
        {
            "name": "Mixed media type with all filters",
            "params": {
                "media_type": "mixed",
                "genres": ["28", "12"],  # Action, Adventure  
                "rating_min": "7.0",
                "year_from": "2020",
                "year_to": "2024",
                "sort": "popular"
            }
        },
        {
            "name": "Custom category",
            "params": {
                "media_type": "mixed",
                "custom_category_id": "123"
            }
        },
        {
            "name": "Database category",
            "params": {
                "media_type": "movie",
                "db_category_type": "requests",
                "db_category_sort": "recent"
            }
        }
    ]
    
    for test_case in test_cases:
        print(f"\n   Testing: {test_case['name']}")
        query_string = build_discover_query_params(**test_case["params"])
        print(f"   Result: {query_string}")
        
        # Check for essential parameters
        if "media_type" in test_case["params"]:
            if f"media_type={test_case['params']['media_type']}" not in query_string:
                print(f"   ❌ Missing media_type parameter!")
            else:
                print(f"   ✅ media_type parameter present")

def analyze_template_context():
    """Analyze what context the template receives"""
    print("\n🎨 Analyzing template context requirements...")
    
    # Read the template file to see what variables it expects
    template_path = "/opt/stoutRequests/app/templates/components/movie_cards_only.html"
    try:
        with open(template_path, 'r') as f:
            template_content = f.read()
            
        # Look for template variables
        import re
        variables = re.findall(r'\{\{\s*([^}]+)\s*\}\}', template_content)
        
        print("   Template variables found:")
        unique_vars = set()
        for var in variables:
            # Clean up the variable name
            clean_var = var.split('|')[0].split('.')[0].strip()
            if clean_var not in unique_vars:
                unique_vars.add(clean_var)
                print(f"     - {clean_var}")
        
        # Check for specific issues mentioned
        if "has_more" in template_content:
            print("   ✅ Template has infinite scroll trigger with has_more check")
        else:
            print("   ❌ Template missing has_more check!")
            
        if "current_query_params" in template_content:
            print("   ✅ Template uses current_query_params for pagination")
        else:
            print("   ❌ Template missing current_query_params!")
            
    except Exception as e:
        print(f"   ❌ Error reading template: {e}")

if __name__ == "__main__":
    print("🚀 Starting infinite scroll debugging...")
    
    # Test pagination behavior
    asyncio.run(test_infinite_scroll_pagination())
    
    # Test query parameter building
    test_query_param_building()
    
    # Analyze template requirements
    analyze_template_context()
    
    print("\n✅ Debugging complete!")