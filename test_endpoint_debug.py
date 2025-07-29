#!/usr/bin/env python3
"""
Debug script to test the discover endpoint logic directly
"""
import sys
sys.path.append('.')

from app.main import convert_rating_to_tmdb_filter, filter_database_category
from app.services.tmdb_service import TMDBService
from app.core.database import engine
from sqlmodel import Session
from fastapi import Request
from unittest.mock import Mock

def test_endpoint_logic():
    print("🔍 Testing endpoint parameter processing...")
    
    # Test the rating conversion function
    rating_filter = convert_rating_to_tmdb_filter("8.0", "tmdb")
    print(f"🎯 Rating conversion: '8.0' -> {rating_filter}")
    
    # Test the database filter function simulation
    mock_request = Mock(spec=Request)
    mock_request.headers = {}
    
    with Session(engine) as session:
        tmdb_service = TMDBService(session)
        
        print("\n🔄 Testing mixed media filter logic (page 1):")
        try:
            # Simulate the main endpoint call for page 1
            # This is what happens on the initial page load
            result = tmdb_service.get_category_content(
                media_type="mixed",
                category="popular",
                page=1,
                vote_average_gte=8.0
            )
            print(f"✅ Page 1 results count: {len(result.get('results', []))}")
            
            if result.get('results'):
                ratings = [item.get('vote_average', 0) for item in result.get('results', [])]
                print(f"✅ Page 1 ratings: min={min(ratings)}, max={max(ratings)}")
            
        except Exception as e:
            print(f"❌ Page 1 error: {e}")
        
        print("\n🔄 Testing mixed media filter logic (page 2):")
        try:
            # Simulate the infinite scroll call for page 2
            # This is what happens when user scrolls down
            result = tmdb_service.get_category_content(
                media_type="mixed",
                category="popular",
                page=2,
                vote_average_gte=8.0
            )
            print(f"✅ Page 2 results count: {len(result.get('results', []))}")
            
            if result.get('results'):
                ratings = [item.get('vote_average', 0) for item in result.get('results', [])]
                print(f"✅ Page 2 ratings: min={min(ratings)}, max={max(ratings)}")
                
                # Show specific examples of low ratings if found
                low_ratings = [item for item in result.get('results', []) if item.get('vote_average', 0) < 8.0]
                if low_ratings:
                    print(f"❌ Found {len(low_ratings)} items with ratings below 8.0:")
                    for item in low_ratings[:3]:  # Show first 3 examples
                        print(f"   - {item.get('title') or item.get('name')}: {item.get('vote_average')}")
            
        except Exception as e:
            print(f"❌ Page 2 error: {e}")

if __name__ == "__main__":
    test_endpoint_logic()