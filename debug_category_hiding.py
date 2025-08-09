#!/usr/bin/env python3
"""Debug script for category hiding functionality"""

import sys
import os
sys.path.append('/opt/stoutRequests')

from app.core.database import engine
from app.main import get_user_categories
from app.models.user_category_preferences import UserCategoryPreferences
from sqlmodel import Session, select

def debug_category_hiding():
    """Debug the category hiding functionality"""
    
    with Session(engine) as session:
        print("=== Category Hiding Debug ===\n")
        
        # Get all users with category preferences
        stmt = select(UserCategoryPreferences)
        all_prefs = session.exec(stmt).all()
        
        # Group by user
        users_with_prefs = {}
        for pref in all_prefs:
            if pref.user_id not in users_with_prefs:
                users_with_prefs[pref.user_id] = []
            users_with_prefs[pref.user_id].append(pref)
        
        print(f"Found {len(users_with_prefs)} users with category preferences:\n")
        
        for user_id, prefs in users_with_prefs.items():
            print(f"User {user_id}:")
            for pref in prefs:
                visibility = "VISIBLE" if pref.is_visible else "HIDDEN"
                print(f"  - {pref.category_id}: {visibility} (order: {pref.display_order})")
            
            print(f"\n  Categories returned by get_user_categories:")
            categories = get_user_categories(user_id, session)
            for cat in categories:
                print(f"    - {cat['id']}: {cat['title']} (order: {cat['order']})")
            
            # Check specifically for recommended-for-you
            recommended_in_prefs = any(p.category_id == 'recommended-for-you' for p in prefs)
            recommended_in_categories = any(c['id'] == 'recommended-for-you' for c in categories)
            recommended_pref = next((p for p in prefs if p.category_id == 'recommended-for-you'), None)
            
            print(f"\n  Recommended category analysis:")
            print(f"    - Has recommended pref in DB: {recommended_in_prefs}")
            if recommended_pref:
                print(f"    - Recommended pref visible: {recommended_pref.is_visible}")
            print(f"    - Recommended in returned categories: {recommended_in_categories}")
            
            print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    debug_category_hiding()