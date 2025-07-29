#!/usr/bin/env python3
"""
Test mixed media pagination logic
"""
from app.services.tmdb_service import TMDBService
from app.core.database import engine
from sqlmodel import Session

def test_mixed_media_pagination():
    print("🔍 Testing mixed media pagination...")
    
    with Session(engine) as session:
        tmdb_service = TMDBService(session)
        
        for page in range(1, 6):
            print(f"\n🎬📺 Testing mixed popular content - Page {page}:")
            
            # Test the category method that's used by the app
            result = tmdb_service.get_category_content(
                media_type="mixed",
                category="popular",
                page=page
            )
            
            print(f"Results: {len(result.get('results', []))}")
            print(f"Total pages: {result.get('total_pages', 'N/A')}")
            print(f"Total results: {result.get('total_results', 'N/A')}")
            
            if len(result.get('results', [])) == 0:
                print("❌ No results returned - stopping")
                break
            
            # Check if has_more would be calculated correctly
            has_more = result.get('total_pages', 1) > page
            print(f"Has more: {has_more}")

if __name__ == "__main__":
    test_mixed_media_pagination()