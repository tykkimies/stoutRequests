#!/usr/bin/env python3
"""
Comprehensive Filter Parameter Mapping Test
Tests all filter combinations across movies, TV shows, and mixed content.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.tmdb_service import TMDBService
from sqlmodel import Session, create_engine

def test_date_parameters():
    """Test date parameter mapping for all media types"""
    print("🧪 Testing Date Parameter Mapping...")
    
    # Create a test session
    engine = create_engine("sqlite:///:memory:")
    session = Session(engine)
    tmdb_service = TMDBService(session)
    
    test_cases = [
        {
            "name": "Movies with year filter 2024-2025",
            "media_type": "movie",
            "category": "popular",
            "primary_release_date_gte": "2024-01-01",
            "primary_release_date_lte": "2025-12-31",
            "expected_params": ["primary_release_date_gte", "primary_release_date_lte"]
        },
        {
            "name": "TV shows with year filter 2024-2025",
            "media_type": "tv", 
            "category": "popular",
            "first_air_date_gte": "2024-01-01",
            "first_air_date_lte": "2025-12-31",
            "expected_params": ["first_air_date_gte", "first_air_date_lte"]
        },
        {
            "name": "Mixed content with movie date parameters",
            "media_type": "mixed",
            "category": "popular",
            "primary_release_date_gte": "2024-01-01",
            "primary_release_date_lte": "2025-12-31",
            "expected_behavior": "Should map to both movie and TV date parameters"
        },
        {
            "name": "Mixed content with TV date parameters",
            "media_type": "mixed",
            "category": "popular", 
            "first_air_date_gte": "2024-01-01",
            "first_air_date_lte": "2025-12-31",
            "expected_behavior": "Should map to both movie and TV date parameters"
        }
    ]
    
    for test_case in test_cases:
        print(f"\n📋 Testing: {test_case['name']}")
        
        try:
            # Build parameters dynamically
            params = {
                "media_type": test_case["media_type"],
                "category": test_case["category"],
                "page": 1
            }
            
            # Add date parameters if present
            if "primary_release_date_gte" in test_case:
                params["primary_release_date_gte"] = test_case["primary_release_date_gte"]
            if "primary_release_date_lte" in test_case:
                params["primary_release_date_lte"] = test_case["primary_release_date_lte"]
            if "first_air_date_gte" in test_case:
                params["first_air_date_gte"] = test_case["first_air_date_gte"]
            if "first_air_date_lte" in test_case:
                params["first_air_date_lte"] = test_case["first_air_date_lte"]
            
            # Call the service method
            result = tmdb_service.get_category_content(**params)
            
            # Validate results
            if result and "results" in result:
                num_results = len(result["results"])
                print(f"   ✅ SUCCESS: Got {num_results} results")
                
                # Check if results have the expected media types
                if test_case["media_type"] == "mixed":
                    media_types = set(item.get("media_type") for item in result["results"])
                    print(f"   📊 Media types in results: {media_types}")
                else:
                    print(f"   📊 Media type: {test_case['media_type']}")
                    
            else:
                print(f"   ❌ FAILED: No results returned")
                
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
    
    session.close()

def test_genre_parameters():
    """Test genre parameter mapping for all media types"""
    print("\n🧪 Testing Genre Parameter Mapping...")
    
    engine = create_engine("sqlite:///:memory:")
    session = Session(engine)
    tmdb_service = TMDBService(session)
    
    test_cases = [
        {
            "name": "Movies with Action genre (28)",
            "media_type": "movie",
            "category": "popular",
            "with_genres": "28"
        },
        {
            "name": "TV shows with Drama genre (18)",
            "media_type": "tv",
            "category": "popular", 
            "with_genres": "18"
        },
        {
            "name": "Mixed content with Action genre",
            "media_type": "mixed",
            "category": "popular",
            "with_genres": "28"
        }
    ]
    
    for test_case in test_cases:
        print(f"\n📋 Testing: {test_case['name']}")
        
        try:
            result = tmdb_service.get_category_content(
                media_type=test_case["media_type"],
                category=test_case["category"],
                with_genres=test_case["with_genres"],
                page=1
            )
            
            if result and "results" in result:
                num_results = len(result["results"])
                print(f"   ✅ SUCCESS: Got {num_results} results")
            else:
                print(f"   ❌ FAILED: No results returned")
                
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
    
    session.close()

def test_studio_network_parameters():
    """Test studio/network parameter mapping"""
    print("\n🧪 Testing Studio/Network Parameter Mapping...")
    
    engine = create_engine("sqlite:///:memory:")
    session = Session(engine)
    tmdb_service = TMDBService(session)
    
    test_cases = [
        {
            "name": "Movies with Disney studio (2)",
            "media_type": "movie",
            "category": "popular",
            "with_companies": "2"
        },
        {
            "name": "TV shows with HBO network (49)",
            "media_type": "tv",
            "category": "popular",
            "with_networks": "49"
        },
        {
            "name": "Mixed content with Disney",
            "media_type": "mixed", 
            "category": "popular",
            "with_companies": "2"
        }
    ]
    
    for test_case in test_cases:
        print(f"\n📋 Testing: {test_case['name']}")
        
        try:
            params = {
                "media_type": test_case["media_type"],
                "category": test_case["category"],
                "page": 1
            }
            
            if "with_companies" in test_case:
                params["with_companies"] = test_case["with_companies"]
            if "with_networks" in test_case:
                params["with_networks"] = test_case["with_networks"]
            
            result = tmdb_service.get_category_content(**params)
            
            if result and "results" in result:
                num_results = len(result["results"])
                print(f"   ✅ SUCCESS: Got {num_results} results")
            else:
                print(f"   ❌ FAILED: No results returned")
                
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
    
    session.close()

def test_combined_filters():
    """Test multiple filters combined"""
    print("\n🧪 Testing Combined Filter Parameters...")
    
    engine = create_engine("sqlite:///:memory:")
    session = Session(engine)
    tmdb_service = TMDBService(session)
    
    test_cases = [
        {
            "name": "Movies: Action + 2024 + Rating 7+",
            "media_type": "movie",
            "category": "popular",
            "with_genres": "28",
            "primary_release_date_gte": "2024-01-01",
            "vote_average_gte": 7.0
        },
        {
            "name": "TV: Drama + 2024 + Rating 8+",
            "media_type": "tv",
            "category": "popular",
            "with_genres": "18",
            "first_air_date_gte": "2024-01-01", 
            "vote_average_gte": 8.0
        },
        {
            "name": "Mixed: Action + 2024 + Rating 7+",
            "media_type": "mixed",
            "category": "popular",
            "with_genres": "28",
            "primary_release_date_gte": "2024-01-01",
            "vote_average_gte": 7.0
        }
    ]
    
    for test_case in test_cases:
        print(f"\n📋 Testing: {test_case['name']}")
        
        try:
            params = {k: v for k, v in test_case.items() if k not in ["name"]}
            params["page"] = 1
            
            result = tmdb_service.get_category_content(**params)
            
            if result and "results" in result:
                num_results = len(result["results"])
                print(f"   ✅ SUCCESS: Got {num_results} results")
                
                # Additional validation for mixed content
                if test_case["media_type"] == "mixed":
                    media_types = set(item.get("media_type") for item in result["results"])
                    print(f"   📊 Mixed content media types: {media_types}")
                    
            else:
                print(f"   ❌ FAILED: No results returned")
                
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
    
    session.close()

if __name__ == "__main__":
    print("🚀 Starting Comprehensive Parameter Mapping Tests\n")
    
    test_date_parameters()
    test_genre_parameters() 
    test_studio_network_parameters()
    test_combined_filters()
    
    print("\n✅ All tests completed!")