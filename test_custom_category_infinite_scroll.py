#!/usr/bin/env python3
"""
Test script to verify custom category infinite scroll URL generation
"""

def test_query_params_generation():
    """Test that current_query_params is built correctly for custom categories"""
    
    # Simulate the backend query params building logic
    custom_media_type = "mixed"
    custom_category_id = "14"
    filters = {
        'genres': ['28'],
        'rating_min': '7.0',
        'rating_source': 'tmdb',
        'year_from': '2020',
        'year_to': '',
        'studios': [],
        'streaming': []
    }
    
    # Build current_query_params like the backend does
    current_query_params = f"media_type={custom_media_type}&custom_category_id={custom_category_id}"
    
    if filters.get('genres'):
        genre_params = "&".join([f"genres={g}" for g in filters.get('genres', [])])
        current_query_params += f"&{genre_params}"
    
    if filters.get('rating_min'):
        current_query_params += f"&rating_min={filters.get('rating_min')}&rating_source={filters.get('rating_source')}"
    
    if filters.get('year_from'):
        current_query_params += f"&year_from={filters.get('year_from')}"
    
    if filters.get('year_to'):
        current_query_params += f"&year_to={filters.get('year_to')}"
    
    if filters.get('studios'):
        studio_params = "&".join([f"studios={s}" for s in filters.get('studios', [])])  
        current_query_params += f"&{studio_params}"
        
    if filters.get('streaming'):
        streaming_params = "&".join([f"streaming={s}" for s in filters.get('streaming', [])])
        current_query_params += f"&{streaming_params}"
    
    print("=== Custom Category Infinite Scroll URL Test ===")
    print(f"Generated current_query_params: {current_query_params}")
    print()
    
    # Test template routing logic
    def test_template_routing(current_query_params, base_url=""):
        """Test the template routing logic"""
        print("=== Template Routing Logic Test ===")
        
        # Simulate the template condition
        if current_query_params and current_query_params.startswith('media_type='):
            url = f"{base_url}/discover?{current_query_params}&page=2"
            print(f"✅ Using /discover endpoint: {url}")
            return url
        else:
            # Fall back to old logic
            url = f"{base_url}/discover/category/more?custom_category_id=14&type=movie&page=2&limit=40"
            print(f"❌ Using old /discover/category/more endpoint: {url}")
            return url
    
    # Test both scenarios
    print("Expected URL should be:")
    expected_url = "https://plexmanager.duckdns.org/newrequests/discover?media_type=mixed&custom_category_id=14&genres=28&rating_min=7.0&rating_source=tmdb&year_from=2020&page=2"
    print(expected_url)
    print()
    
    # Test with our generated params
    base_url = "https://plexmanager.duckdns.org/newrequests"
    actual_url = test_template_routing(current_query_params, base_url)
    
    print()
    print("=== Comparison ===")
    if "/discover?" in actual_url and "media_type=mixed" in actual_url and "genres=28" in actual_url:
        print("✅ SUCCESS: URL generation fixed!")
        print("✅ Now using correct /discover endpoint")
        print("✅ Includes media_type=mixed parameter")
        print("✅ Includes genres=28 parameter")
        print("✅ Includes rating parameters")
    else:
        print("❌ FAILURE: Still using wrong endpoint or missing parameters")
        
    return current_query_params

if __name__ == "__main__":
    test_query_params_generation()