#!/usr/bin/env python3
"""Test script to verify category hiding functionality"""

import requests

def test_hide_recommended_category():
    # Test data - simulating form submission to hide recommended category
    form_data = {
        'recently-added_visible': 'on',
        'recently-added_order': '1',
        'recent-requests_visible': 'on', 
        'recent-requests_order': '2',
        'recommended-for-you_order': '3',  # Note: no _visible means hidden
        'trending-movies_visible': 'on',
        'trending-movies_order': '4',
        'popular-movies_visible': 'on',
        'popular-movies_order': '5',
        'trending-tv_visible': 'on',
        'trending-tv_order': '6',
        'popular-tv_visible': 'on',
        'popular-tv_order': '7'
    }
    
    # First, get the current page to establish session
    session = requests.Session()
    
    try:
        # Test the customization endpoint
        response = session.post('http://localhost:8002/discover/categories/customize', data=form_data)
        print(f"Response status: {response.status_code}")
        print(f"Response content: {response.text[:200]}")
        
        if response.status_code == 200:
            print("✅ Category customization request successful")
        else:
            print("❌ Category customization request failed")
            
    except Exception as e:
        print(f"❌ Error testing category hide: {e}")

if __name__ == "__main__":
    test_hide_recommended_category()