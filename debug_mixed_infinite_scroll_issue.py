#!/usr/bin/env python3

import requests
import json
import sys

# Test the infinite scroll for mixed content to see what's actually being returned

def test_mixed_content_infinite_scroll():
    """
    Test the /discover/category/more endpoint with mixed content type
    to see if it returns both movies and TV shows on page 2
    """
    
    base_url = "http://localhost:8000"
    
    # Test with basic parameters for mixed content
    params = {
        'type': 'mixed',
        'media_type': 'mixed', 
        'sort': 'popular',
        'page': 2,  # Page 2 to test infinite scroll
        'limit': 40
    }
    
    print("🔍 Testing mixed content infinite scroll...")
    print(f"🔍 URL: {base_url}/discover/category/more")
    print(f"🔍 Params: {params}")
    
    try:
        response = requests.get(f"{base_url}/discover/category/more", params=params)
        print(f"🔍 Status: {response.status_code}")
        
        if response.status_code == 200:
            # Parse the HTML response to see what media types are included
            html = response.text
            print(f"🔍 Response length: {len(html)} characters")
            
            # Look for specific indicators of movies vs TV shows
            movie_indicators = html.count('movie-card') + html.count('media_type=movie') + html.count('"movie"')
            tv_indicators = html.count('tv-card') + html.count('media_type=tv') + html.count('"tv"')
            
            print(f"🔍 Movie indicators found: {movie_indicators}")
            print(f"🔍 TV indicators found: {tv_indicators}")
            
            # Look for actual titles that might indicate the content type
            if 'data-media-type="movie"' in html:
                movie_titles = html.count('data-media-type="movie"')
                print(f"🎬 Found {movie_titles} movies")
            
            if 'data-media-type="tv"' in html:
                tv_titles = html.count('data-media-type="tv"')
                print(f"📺 Found {tv_titles} TV shows")
            
            # If both are 0, something is wrong
            if movie_indicators == 0 and tv_indicators == 0:
                print("❌ NO MEDIA TYPE INDICATORS FOUND - This suggests the response is empty or malformed")
                print("🔍 First 500 characters of response:")
                print(html[:500])
            elif tv_indicators == 0:
                print("❌ NO TV SHOWS FOUND - This confirms the bug: only movies are being returned for mixed content!")
            elif movie_indicators == 0:
                print("❌ NO MOVIES FOUND - Unexpected: only TV shows returned")
            else:
                print("✅ Both movies and TV shows found - mixed content working correctly")
                
        else:
            print(f"❌ Error response: {response.status_code}")
            print(f"❌ Response: {response.text[:500]}")
            
    except Exception as e:
        print(f"❌ Error making request: {e}")

def test_mixed_content_discover_endpoint():
    """
    Test the discover endpoint directly to see if TMDB service is working
    """
    print("\n" + "="*50)
    print("🔍 Testing mixed content with no content sources (discover endpoint)...")
    
    params = {
        'type': 'mixed',
        'media_type': 'mixed',
        'sort': 'popular', 
        'page': 2,
        'limit': 40,
        'content_sources': []  # Empty to force discover endpoint
    }
    
    try:
        response = requests.get("http://localhost:8000/discover/category/more", params=params)
        print(f"🔍 Status: {response.status_code}")
        
        if response.status_code == 200:
            html = response.text
            movie_count = html.count('data-media-type="movie"')
            tv_count = html.count('data-media-type="tv"')
            
            print(f"🎬 Movies found: {movie_count}")
            print(f"📺 TV shows found: {tv_count}")
            
            if tv_count == 0:
                print("❌ BUG CONFIRMED: Discover endpoint for mixed content only returns movies!")
            else:
                print("✅ Discover endpoint working correctly for mixed content")
                
    except Exception as e:
        print(f"❌ Error: {e}")

def test_mixed_content_with_sources():
    """
    Test mixed content with specific content sources
    """
    print("\n" + "="*50)
    print("🔍 Testing mixed content with content sources...")
    
    params = {
        'type': 'mixed',
        'media_type': 'mixed',
        'sort': 'popular',
        'page': 2,
        'limit': 40,
        'content_sources': ['popular', 'trending']  # Specific sources
    }
    
    try:
        response = requests.get("http://localhost:8000/discover/category/more", params=params)
        print(f"🔍 Status: {response.status_code}")
        
        if response.status_code == 200:
            html = response.text
            movie_count = html.count('data-media-type="movie"')
            tv_count = html.count('data-media-type="tv"')
            
            print(f"🎬 Movies found: {movie_count}")
            print(f"📺 TV shows found: {tv_count}")
            
            if tv_count == 0:
                print("❌ BUG: Content sources path also only returns movies!")
            else:
                print("✅ Content sources path working correctly for mixed content")
                
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🔍 Debug: Mixed Content Infinite Scroll Issue")
    print("="*60)
    
    test_mixed_content_infinite_scroll()
    test_mixed_content_discover_endpoint()
    test_mixed_content_with_sources()
    
    print("\n" + "="*60)
    print("🔍 Debug complete. Check the output above to identify the exact issue.")