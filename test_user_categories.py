#!/usr/bin/env python3
"""Test script to verify get_user_categories function"""

import sys
import os
sys.path.append('/opt/stoutRequests')

from app.core.database import engine
from app.main import get_user_categories
from sqlmodel import Session

def test_user_categories():
    """Test the get_user_categories function with user 207 (stoutp9)"""
    
    with Session(engine) as session:
        # Test with user 207 who should have recommended-for-you hidden
        user_id = 207
        categories = get_user_categories(user_id, session)
        
        print(f"Categories for user {user_id}:")
        print("-" * 50)
        
        recommended_found = False
        for category in categories:
            print(f"- {category['id']}: {category['title']} (order: {category['order']})")
            if category['id'] == 'recommended-for-you':
                recommended_found = True
        
        print(f"\nTotal categories: {len(categories)}")
        print(f"Recommended category found: {recommended_found}")
        
        if recommended_found:
            print("❌ ERROR: Recommended category should be hidden but is still showing")
        else:
            print("✅ SUCCESS: Recommended category is properly hidden")

if __name__ == "__main__":
    test_user_categories()