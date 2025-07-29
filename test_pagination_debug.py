#!/usr/bin/env python3
"""
Debug script to test TMDB pagination limits
"""
from app.services.tmdb_service import TMDBService
from app.core.database import engine
from sqlmodel import Session

def test_pagination():
    print("🔍 Testing TMDB pagination limits...")
    
    with Session(engine) as session:
        tmdb_service = TMDBService(session)
        
        print("\n📊 Testing Movie Discovery (no filters):")
        for page in range(1, 6):
            response = tmdb_service.discover_movies(page=page, sort_by="popularity.desc")
            print(f"Page {page}: {len(response.get('results', []))} results, total_pages: {response.get('total_pages', 0)}")
            if response.get('total_pages', 0) == 0:
                break
        
        print("\n📺 Testing TV Discovery (no filters):")
        for page in range(1, 6):
            response = tmdb_service.discover_tv(page=page, sort_by="popularity.desc")
            print(f"Page {page}: {len(response.get('results', []))} results, total_pages: {response.get('total_pages', 0)}")
            if response.get('total_pages', 0) == 0:
                break
                
        print("\n🎬 Testing Action Movie Discovery (with genre 28):")
        for page in range(1, 6):
            response = tmdb_service.discover_movies(page=page, sort_by="popularity.desc", with_genres="28")
            print(f"Page {page}: {len(response.get('results', []))} results, total_pages: {response.get('total_pages', 0)}")
            if response.get('total_pages', 0) == 0:
                break
                
        print("\n📺 Testing Action TV Discovery (with genre 10759):")
        for page in range(1, 6):
            response = tmdb_service.discover_tv(page=page, sort_by="popularity.desc", with_genres="10759")
            print(f"Page {page}: {len(response.get('results', []))} results, total_pages: {response.get('total_pages', 0)}")
            if response.get('total_pages', 0) == 0:
                break

if __name__ == "__main__":
    test_pagination()