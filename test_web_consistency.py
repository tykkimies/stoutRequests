#\!/usr/bin/env python3
"""
Test what URLs are actually being called and what responses they give
"""
import requests

def test_web_requests():
    print("🔍 Testing actual web requests for trending movies...")
    
    base_url = "http://localhost:8001/newrequests"
    
    # Test the initial expand request (what happens when you click "See More")
    print("\n📋 Testing initial expand request:")
    url = f"{base_url}/discover/category/expanded"
    params = {"type": "movie", "sort": "trending", "page": 1}
    
    try:
        response = requests.get(url, params=params)
        print(f"URL: {url}?{requests.utils.urlencode(params)}")
        print(f"Status: {response.status_code}")
        
        # Look for pagination info in the response
        if "has_more" in response.text:
            print("✅ Response contains has_more")
        if "load-more-trigger" in response.text:
            print("✅ Response contains infinite scroll trigger")
        if "total_pages" in response.text:
            print("✅ Response contains total_pages")
            
        # Check for the next page URL in the infinite scroll trigger
        if 'page=2' in response.text:
            print("✅ Next page URL found")
        else:
            print("❌ No next page URL found")
            
    except requests.exceptions.ConnectionError:
        print("❌ Server not running - can't test web requests")
        print("💡 Please start the server with: python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001")
        return
    
    # Test the infinite scroll request (what happens when you scroll down)
    print("\n🔄 Testing infinite scroll request:")
    url = f"{base_url}/discover/category/more"
    params = {"type": "movie", "sort": "trending", "page": 2}
    
    try:
        response = requests.get(url, params=params)
        print(f"URL: {url}?{requests.utils.urlencode(params)}")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            # Check if has_more is in the response for page 2
            if "has_more" in response.text:
                print("✅ Page 2 response contains has_more")
            if "load-more-trigger" in response.text:
                print("✅ Page 2 response contains infinite scroll trigger")
            if 'page=3' in response.text:
                print("✅ Page 3 URL found in response")
            else:
                print("❌ No page 3 URL found - this might be why it stops\!")
        else:
            print(f"❌ Page 2 request failed: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error testing infinite scroll: {e}")

if __name__ == "__main__":
    test_web_requests()
EOF < /dev/null
