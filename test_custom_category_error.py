#!/usr/bin/env python3
"""
Test script to debug custom category error
"""
import requests
import sys

def test_custom_category():
    # Test the endpoint that's failing
    url = "http://localhost:8001/newrequests/discover"
    params = {
        "media_type": "mixed",
        "custom_category_id": "14", 
        "genres": "28",
        "page": "2"
    }
    
    headers = {
        "HX-Request": "true",
        "HX-Target": "results-grid"
    }
    
    print(f"Testing URL: {url}")
    print(f"Parameters: {params}")
    print(f"Headers: {headers}")
    
    try:
        response = requests.get(url, params=params, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response Text: {response.text}")
        
        if response.status_code != 200:
            print(f"Error response: {response.text}")
        
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_custom_category()