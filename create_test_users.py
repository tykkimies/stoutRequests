#!/usr/bin/env python3
"""
Script to create test users for testing the request visibility system
"""

import sys
import os

# Add the app directory to the path
sys.path.append('/opt/stoutRequests')

from sqlmodel import Session, select
from app.core.database import engine
from app.models.user import User

def create_test_users():
    """Create default test users"""
    with Session(engine) as session:
        # Test users to create
        test_users = [
            {
                "username": "testuser",
                "full_name": "Regular Test User",
                "is_admin": False
            },
            {
                "username": "testadmin", 
                "full_name": "Admin Test User",
                "is_admin": True
            },
            {
                "username": "basicuser",
                "full_name": "Basic User", 
                "is_admin": False
            }
        ]
        
        created_users = []
        
        for user_data in test_users:
            # Check if user already exists
            existing = session.exec(
                select(User).where(User.username == user_data["username"])
            ).first()
            
            if existing:
                print(f"❌ User '{user_data['username']}' already exists")
                continue
            
            # Find next available negative plex_id
            lowest_test_id = session.exec(
                select(User.plex_id).where(User.plex_id < 0).order_by(User.plex_id)
            ).first()
            test_plex_id = (lowest_test_id - 1) if lowest_test_id else -1
            
            # Create user
            test_user = User(
                plex_id=test_plex_id,
                username=user_data["username"],
                email=f"{user_data['username']}@test.local",
                full_name=user_data["full_name"],
                is_admin=user_data["is_admin"],
                is_active=True
            )
            
            session.add(test_user)
            created_users.append(user_data["username"])
        
        if created_users:
            session.commit()
            print(f"✅ Created {len(created_users)} test users:")
            for username in created_users:
                print(f"   - {username}")
        else:
            print("ℹ️  No new test users created")

if __name__ == "__main__":
    create_test_users()