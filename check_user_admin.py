#!/usr/bin/env python3
"""
Check user admin status and make first user admin if needed
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, '/opt/stoutRequests')

def check_and_fix_admin():
    try:
        from app.core.database import engine
        from app.models.user import User
        from sqlmodel import Session, select
        
        with Session(engine) as session:
            # Get all users
            all_users = session.exec(select(User)).all()
            print(f"📊 Found {len(all_users)} users:")
            
            for user in all_users:
                print(f"   • {user.username} (ID: {user.id}) - Admin: {user.is_admin} - Active: {user.is_active}")
            
            # Check if any admin exists
            admin_users = session.exec(select(User).where(User.is_admin == True)).all()
            print(f"\n👑 Admin users: {len(admin_users)}")
            
            if not admin_users and all_users:
                # Make the first user admin
                first_user = all_users[0]
                print(f"\n🔧 Making first user '{first_user.username}' an admin...")
                
                first_user.is_admin = True
                first_user.is_active = True
                session.add(first_user)
                session.commit()
                session.refresh(first_user)
                
                print(f"✅ User '{first_user.username}' is now an admin!")
                
            elif admin_users:
                print(f"\n✅ Admin users already exist:")
                for admin in admin_users:
                    print(f"   • {admin.username}")
            else:
                print(f"\n⚠️ No users found in database")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_and_fix_admin()