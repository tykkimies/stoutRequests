#!/usr/bin/env python3

"""
Debug script to test infinite scroll mixed content issue.
This simulates the infinite scroll request that's only returning movies.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlmodel import Session
from app.core.database import engine
from app.services.tmdb_service import TMDBService

def test_mixed_content_infinite_scroll():
    """Test the get_category_content method with mixed media type."""
    
    print("🔍 TESTING MIXED CONTENT INFINITE SCROLL")
    print("=" * 60)
    
    with Session(engine) as session:
        tmdb_service = TMDBService(session)
        
        # Test the parameters from the user's debug output
        print("Testing with user's reported parameters:")
        print("- media_type='mixed'")
        print("- category='trending'") 
        print("- page=2")
        print("- with_genres='28' (Action)")
        print()
        
        try:
            # This simulates the call made in discover_category_more
            result = tmdb_service.get_category_content(
                media_type='mixed',
                category='trending',
                page=2,
                with_genres='28'  # Action genre
            )
            
            print("🔍 FINAL RESULT ANALYSIS:")
            print(f"- Total results: {len(result.get('results', []))}")
            print(f"- Total pages: {result.get('total_pages', 0)}")
            print(f"- Current page: {result.get('page', 0)}")
            
            results = result.get('results', [])
            if results:
                movie_count = len([r for r in results if r.get('media_type') == 'movie'])
                tv_count = len([r for r in results if r.get('media_type') == 'tv'])
                unknown_count = len([r for r in results if r.get('media_type') not in ['movie', 'tv']])
                
                print(f"- Movies: {movie_count}")
                print(f"- TV shows: {tv_count}")
                print(f"- Unknown media type: {unknown_count}")
                
                print("\n📝 SAMPLE RESULTS:")
                for i, item in enumerate(results[:5]):
                    title = item.get('title', item.get('name', 'Unknown'))
                    media_type = item.get('media_type', 'NOT SET')
                    popularity = item.get('popularity', 0)
                    print(f"  [{i+1}] {title} -> {media_type} (popularity: {popularity})")
                
                # Check if the issue is here
                if tv_count == 0 and movie_count > 0:
                    print("\n❌ ISSUE CONFIRMED: Only movies returned, no TV shows!")
                    print("This confirms the reported bug.")
                elif tv_count > 0 and movie_count > 0:
                    print("\n✅ MIXED CONTENT WORKING: Both movies and TV shows returned.")
                else:
                    print(f"\n⚠️ UNEXPECTED: movie_count={movie_count}, tv_count={tv_count}")
            
        except Exception as e:
            print(f"❌ ERROR in test: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_mixed_content_infinite_scroll()