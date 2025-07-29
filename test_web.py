#!/usr/bin/env python3
import requests

print("🔍 Testing trending movies web requests...")

# Test infinite scroll for trending movies
url = "http://localhost:8001/newrequests/discover/category/more"
for page in [1, 2, 3]:
    params = {"type": "movie", "sort": "trending", "page": page}
    try:
        response = requests.get(url, params=params)
        print(f"\n📋 Page {page}: Status {response.status_code}")
        
        if response.status_code == 200:
            text = response.text.lower()
            has_trigger = "load-more-trigger" in text
            next_page = f"page={page + 1}" in text
            print(f"   Has infinite scroll trigger: {has_trigger}")
            print(f"   Has next page URL: {next_page}")
            
            if not has_trigger:
                print(f"   ❌ Missing infinite scroll - pagination stops here!")
                break
        else:
            print(f"   ❌ Request failed: {response.text[:200]}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        break