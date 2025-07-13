#!/usr/bin/env python3
"""
Test user deletion functionality (dry run)
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, '/opt/stoutRequests')

def test_user_delete():
    try:
        from app.core.database import engine
        from app.models.user import User
        from app.models.media_request import MediaRequest
        from sqlmodel import Session, select
        
        with Session(engine) as session:
            # Get all users
            all_users = session.exec(select(User)).all()
            print(f"📊 Found {len(all_users)} total users:")
            
            for user in all_users:
                # Check if user has requests
                request_statement = select(MediaRequest).where(MediaRequest.user_id == user.id)
                user_requests = session.exec(request_statement).all()
                
                print(f"   • {user.username} (ID: {user.id}) - Admin: {user.is_admin} - Active: {user.is_active}")
                print(f"     Requests: {len(user_requests)}")
                
                if len(user_requests) > 0:
                    print(f"     ⚠️ This user has {len(user_requests)} requests - deletion would be blocked")
                else:
                    print(f"     ✅ This user can be safely deleted")
                    
            print(f"\n🔍 Delete functionality rules:")
            print(f"   • Users cannot delete themselves")
            print(f"   • Users with existing requests cannot be deleted (safety measure)")
            print(f"   • Admin confirmation required with warning")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_user_delete()