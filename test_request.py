#!/usr/bin/env python3
"""
Test media request creation
"""
import sys
import os
import requests
import json

# Add the app directory to the path
sys.path.insert(0, '/opt/stoutRequests')

def test_request():
    try:
        # Test data similar to what the frontend sends
        test_data = {
            "tmdb_id": 19995,
            "media_type": "movie", 
            "title": "Avatar",
            "overview": "Test overview",
            "poster_path": "/test.jpg",
            "release_date": "2009-12-18"
        }
        
        # Test with local server
        url = "http://localhost:8001/requests/"
        
        print(f"🔍 Testing request creation...")
        print(f"   URL: {url}")
        print(f"   Data: {test_data}")
        
        # Try JSON request
        response = requests.post(url, json=test_data)
        print(f"📊 JSON Response: {response.status_code}")
        if response.status_code != 200:
            print(f"   Error: {response.text}")
        
        # Try form data request
        response2 = requests.post(url, data=test_data)
        print(f"📊 Form Response: {response2.status_code}")
        if response2.status_code != 200:
            print(f"   Error: {response2.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_request()