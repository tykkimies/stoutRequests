#!/usr/bin/env python3
"""Simulate the exact category hiding workflow"""

import sys
import os
sys.path.append('/opt/stoutRequests')

from app.core.database import engine
from app.main import get_user_categories
from app.models.user_category_preferences import UserCategoryPreferences
from sqlmodel import Session, select
from datetime import datetime

def simulate_form_submission():
    """Simulate what happens when user unchecks recommended-for-you"""
    
    with Session(engine) as session:
        user_id = 207  # User stoutp9
        
        print("=== CATEGORY HIDING SIMULATION ===\n")
        
        # Step 1: Show current state
        print("📋 Current state:")
        categories = get_user_categories(user_id, session)
        recommended_present = any(c['id'] == 'recommended-for-you' for c in categories)
        print(f"  - Recommended category visible: {recommended_present}")
        
        # Get current preferences
        stmt = select(UserCategoryPreferences).where(
            UserCategoryPreferences.user_id == user_id,
            UserCategoryPreferences.category_id == 'recommended-for-you'
        )
        current_pref = session.exec(stmt).first()
        if current_pref:
            print(f"  - Database shows: is_visible={current_pref.is_visible}, order={current_pref.display_order}")
        
        # Step 2: Simulate form submission (user unchecks recommended-for-you)
        print(f"\n🎭 Simulating form submission (uncheck recommended-for-you)...")
        
        # This simulates the form data when user unchecks recommended-for-you but leaves others checked
        simulated_form_data = {
            'recently-added_visible': 'on',     # Checked
            'recently-added_order': '1',
            'recent-requests_visible': 'on',    # Checked
            'recent-requests_order': '2',
            # Note: recommended-for-you_visible is NOT in form data (unchecked)
            'recommended-for-you_order': '3',   # But order is still sent
            'trending-movies_visible': 'on',    # Checked
            'trending-movies_order': '4',
            'popular-movies_visible': 'on',     # Checked
            'popular-movies_order': '5',
        }
        
        # Step 3: Process form data (like the endpoint does)
        category_updates = {}
        
        for key, value in simulated_form_data.items():
            if key.endswith('_visible'):
                cat_id = key.replace('_visible', '')
                if cat_id not in category_updates:
                    category_updates[cat_id] = {'visible': False, 'order': 0}
                category_updates[cat_id]['visible'] = value == 'on'
            elif key.endswith('_order'):
                cat_id = key.replace('_order', '')
                if cat_id not in category_updates:
                    category_updates[cat_id] = {'visible': False, 'order': 0}
                try:
                    category_updates[cat_id]['order'] = int(value)
                except (ValueError, TypeError):
                    category_updates[cat_id]['order'] = 0
        
        print("📝 Processed category updates:")
        for cat_id, prefs in category_updates.items():
            print(f"  - {cat_id}: visible={prefs['visible']}, order={prefs['order']}")
        
        # Step 4: Apply updates to database
        print(f"\n💾 Applying database updates...")
        for cat_id, prefs in category_updates.items():
            stmt = select(UserCategoryPreferences).where(
                UserCategoryPreferences.user_id == user_id,
                UserCategoryPreferences.category_id == cat_id
            )
            existing_pref = session.exec(stmt).first()
            
            if existing_pref:
                old_visible = existing_pref.is_visible
                existing_pref.is_visible = prefs['visible']
                existing_pref.display_order = prefs['order']
                existing_pref.updated_at = datetime.utcnow()
                print(f"  - {cat_id}: {old_visible} → {prefs['visible']}")
            else:
                new_pref = UserCategoryPreferences(
                    user_id=user_id,
                    category_id=cat_id,
                    is_visible=prefs['visible'],
                    display_order=prefs['order']
                )
                session.add(new_pref)
                print(f"  - {cat_id}: NEW → {prefs['visible']}")
        
        session.commit()
        
        # Step 5: Verify result
        print(f"\n✅ Verification:")
        categories_after = get_user_categories(user_id, session)
        recommended_present_after = any(c['id'] == 'recommended-for-you' for c in categories_after)
        print(f"  - Recommended category visible after update: {recommended_present_after}")
        
        if recommended_present and not recommended_present_after:
            print(f"  🎉 SUCCESS: Category was successfully hidden!")
        elif not recommended_present and not recommended_present_after:
            print(f"  ℹ️  ALREADY HIDDEN: Category was already hidden")
        elif recommended_present_after:
            print(f"  ❌ FAILURE: Category should be hidden but is still visible")
        else:
            print(f"  🤔 UNEXPECTED: Category appeared when it should stay hidden")

if __name__ == "__main__":
    simulate_form_submission()