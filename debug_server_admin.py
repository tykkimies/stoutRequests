#!/usr/bin/env python3
"""
Debug script to identify the actual server admin account
"""
import sys
sys.path.append('/opt/stoutRequests')

from sqlmodel import Session, select
from app.core.database import get_session
from app.models import User
from app.models.user_permissions import UserPermissions

def debug_server_admin():
    """Find the server admin account"""
    print("🔍 Server Admin Account Debug")
    print("=" * 50)
    
    # Get database session
    session = next(get_session())
    
    # Get all users ordered by creation date (first user is likely server admin)
    all_users = session.exec(select(User).order_by(User.created_at)).all()
    
    print(f"📊 Found {len(all_users)} total users:")
    for i, user in enumerate(all_users):
        print(f"\n{i+1}. User: {user.username} (ID: {user.id})")
        print(f"   - Is Admin: {user.is_admin}")
        print(f"   - Created: {user.created_at}")
        print(f"   - Role: {getattr(user, 'role', 'No role field')}")
        print(f"   - Email: {getattr(user, 'email', 'No email')}")
        print(f"   - Auth Provider: {getattr(user, 'auth_provider', 'No auth provider')}")
        
        # Check permissions
        user_perms = session.get(UserPermissions, user.id)
        if user_perms:
            print(f"   - Can request movies: {user_perms.can_request_movies}")
            print(f"   - Can request TV: {user_perms.can_request_tv}")
            print(f"   - Can request 4K: {user_perms.can_request_4k}")
        else:
            print(f"   - No permissions record")
        
        # Mark first user (likely server admin)
        if i == 0:
            print(f"   ⭐ LIKELY SERVER ADMIN (first created)")
        
        # Mark admin users
        if user.is_admin:
            print(f"   👑 ADMIN USER")

if __name__ == "__main__":
    debug_server_admin()