#!/usr/bin/env python3
"""
Debug script to test rating filter functionality
"""
from app.services.tmdb_service import TMDBService
from app.core.database import engine
from sqlmodel import Session

def test_rating_filter():
    print("🔍 Testing TMDB rating filter...")
    
    with Session(engine) as session:
        tmdb_service = TMDBService(session)
        
        print("\n🎬 Testing Movie Discovery with 8.0+ rating filter:")
        movie_response = tmdb_service.discover_movies(
            page=1, 
            sort_by="popularity.desc",
            vote_average_gte=8.0
        )
        
        print("\n📺 Testing TV Discovery with 8.0+ rating filter:")
        tv_response = tmdb_service.discover_tv(
            page=1,
            sort_by="popularity.desc", 
            vote_average_gte=8.0
        )
        
        print("\n🔄 Testing Mixed Media Discovery with 8.0+ rating filter:")
        mixed_response = tmdb_service.get_category_content(
            media_type="mixed",
            category="popular", 
            page=1,
            vote_average_gte=8.0
        )
        
        print("\n✅ Test completed!")

if __name__ == "__main__":
    test_rating_filter()