#!/usr/bin/env python3
"""
Emergency admin access script - bypasses Plex OAuth rate limits
"""

import sys
import os
from datetime import timedelta

# Add the app directory to the path
sys.path.append('/opt/stoutRequests')

from sqlmodel import Session, select
from app.core.database import engine
from app.models.user import User
from app.core.auth import create_access_token

def create_emergency_admin_token():
    """Create an emergency admin access token"""
    with Session(engine) as session:
        # Find the first admin user
        admin_statement = select(User).where(User.is_admin == True).order_by(User.id)
        admin_user = session.exec(admin_statement).first()
        
        if not admin_user:
            print("❌ No admin user found!")
            return None
        
        # Create a long-lived token (24 hours)
        token = create_access_token(
            data={"sub": admin_user.username}, 
            expires_delta=timedelta(hours=24)
        )
        
        print(f"✅ Emergency admin token created for: {admin_user.username}")
        print(f"🔑 Token: {token}")
        print("\n📋 How to use:")
        print("1. Open browser developer tools (F12)")
        print("2. Go to Application/Storage > Cookies")
        print("3. Add a new cookie:")
        print(f"   Name: access_token")
        print(f"   Value: {token}")
        print(f"   Domain: localhost")
        print(f"   Path: /")
        print("4. Refresh the page - you'll be logged in!")
        
        return token

if __name__ == "__main__":
    print("🚨 Emergency Admin Access Tool")
    print("===============================")
    create_emergency_admin_token()