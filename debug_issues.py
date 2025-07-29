#!/usr/bin/env python3
"""
Debug script to test custom category expansion and recent requests issues.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from app.main import app
from sqlmodel import Session, select
from app.core.database import get_session
from app.models.user_custom_category import UserCustomCategory
from app.models.media_request import MediaRequest

# Create test client
client = TestClient(app)

# Test custom category logic
def test_custom_category_data():
    """Test if custom categories exist and have proper filter data."""
    print("\n=== Testing Custom Category Data ===")
    
    # Get a database session
    session = next(get_session())
    
    try:
        # Check for existing custom categories
        stmt = select(UserCustomCategory).where(UserCustomCategory.is_active == True)
        custom_categories = session.exec(stmt).all()
        
        print(f"Found {len(custom_categories)} active custom categories")
        
        for category in custom_categories:
            print(f"\nCategory: {category.name} (ID: {category.id})")
            print(f"  User ID: {category.user_id}")
            print(f"  Media Type: {category.media_type}")
            print(f"  Genres: {category.genres}")
            print(f"  Rating: {category.rating_min} ({category.rating_source})")
            print(f"  Years: {category.year_from} - {category.year_to}")
            print(f"  Studios: {category.studios}")
            print(f"  Streaming: {category.streaming}")
            
            # Test the to_category_dict method
            try:
                category_dict = category.to_category_dict()
                print(f"  Category dict filters: {category_dict['filters']}")
            except Exception as e:
                print(f"  ERROR in to_category_dict: {e}")
                
    except Exception as e:
        print(f"Error testing custom categories: {e}")
    finally:
        session.close()

# Test recent requests logic
def test_recent_requests_data():
    """Test if recent requests exist and can be queried."""
    print("\n=== Testing Recent Requests Data ===")
    
    # Get a database session
    session = next(get_session())
    
    try:
        # Check for existing media requests
        stmt = select(MediaRequest).order_by(MediaRequest.created_at.desc()).limit(10)
        recent_requests = session.exec(stmt).all()
        
        print(f"Found {len(recent_requests)} recent requests")
        
        for request in recent_requests:
            print(f"\nRequest: {request.title} (ID: {request.id})")
            print(f"  TMDB ID: {request.tmdb_id}")
            print(f"  Media Type: {request.media_type}")
            print(f"  Status: {request.status}")
            print(f"  User ID: {request.user_id}")
            print(f"  Created: {request.created_at}")
                
    except Exception as e:
        print(f"Error testing recent requests: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

# Test endpoint responses
def test_custom_category_endpoint():
    """Test custom category expansion endpoint."""
    print("\n=== Testing Custom Category Endpoint ===")
    
    # Get a database session to find a custom category
    session = next(get_session())
    
    try:
        stmt = select(UserCustomCategory).where(UserCustomCategory.is_active == True).limit(1)
        category = session.exec(stmt).first()
        
        if not category:
            print("No custom categories found to test")
            return
            
        print(f"Testing custom category: {category.name} (ID: {category.id})")
        
        # Test the discover_category_expanded endpoint with custom category
        response = client.get(f"/discover/category/expanded?custom_category_id={category.id}&type=movie&page=1")
        print(f"Response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error response: {response.text[:500]}...")
        else:
            print("Custom category endpoint responded successfully")
            
    except Exception as e:
        print(f"Error testing custom category endpoint: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

def test_recent_requests_endpoint():
    """Test recent requests endpoint."""
    print("\n=== Testing Recent Requests Endpoint ===")
    
    try:
        # Test the discover endpoint for recent requests
        response = client.get("/discover?type=requests&sort=recent&view=horizontal")
        print(f"Response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error response: {response.text[:500]}...")
        else:
            print("Recent requests endpoint responded successfully")
            
    except Exception as e:
        print(f"Error testing recent requests endpoint: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Starting debug analysis...")
    
    test_custom_category_data()
    test_recent_requests_data()
    test_custom_category_endpoint()
    test_recent_requests_endpoint()
    
    print("\nDebug analysis complete.")
