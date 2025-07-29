#!/usr/bin/env python3
"""
Test trending movies pagination to see why it stops at 2 pages
"""
from app.services.tmdb_service import TMDBService
from app.core.database import engine
from sqlmodel import Session

def test_trending_movies():
    print("🔍 Testing trending movies pagination...")
    
    with Session(engine) as session:
        tmdb_service = TMDBService(session)
        
        for page in range(1, 6):
            print(f"\n🔥 Testing trending movies - Page {page}:")
            
            # Test the get_category_content method which is used by discover_category_more
            result = tmdb_service.get_category_content(
                media_type="movie",
                category="trending", 
                page=page
            )
            
            results = result.get('results', [])
            total_pages = result.get('total_pages', 1)
            
            print(f"Results: {len(results)} items")
            print(f"Total pages: {total_pages}")
            print(f"Has more calculated: {page < total_pages and len(results) > 0}")
            
            if len(results) == 0:
                print("❌ No results returned - stopping")
                break
                
            if total_pages <= page:
                print(f"❌ Reached max pages: {page} >= {total_pages}")
                break

if __name__ == "__main__":
    test_trending_movies()