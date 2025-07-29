#!/usr/bin/env python3
"""
Test the specific user scenario: custom category with Action genre not working for TV.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.tmdb_service import TMDBService
from app.core.database import engine
from sqlmodel import Session

def test_action_mixed_content():
    """Test Action genre in mixed content - the main user issue"""
    print("Testing Action genre (ID 28) in mixed content...")
    
    with Session(engine) as session:
        tmdb_service = TMDBService(session)
        
        result = tmdb_service.get_category_content(
            media_type="mixed",
            category="popular", 
            page=1,
            with_genres="28"  # Action genre
        )
        
        results = result.get('results', [])
        movies = [r for r in results if r.get('media_type') == 'movie']
        tv_shows = [r for r in results if r.get('media_type') == 'tv']
        
        print(f"Results: {len(results)} total ({len(movies)} movies, {len(tv_shows)} TV shows)")
        
        if len(movies) > 0 and len(tv_shows) > 0:
            print("✅ SUCCESS: Both movies and TV shows found!")
            print("🎯 User's Action genre issue is FIXED!")
            
            print("Example movies:")
            for movie in movies[:3]:
                print(f"  - {movie.get('title', 'Unknown')}")
            
            print("Example TV shows:")
            for show in tv_shows[:3]:
                print(f"  - {show.get('name', 'Unknown')}")
        else:
            print("❌ Issue not fully resolved")

if __name__ == "__main__":
    test_action_mixed_content()