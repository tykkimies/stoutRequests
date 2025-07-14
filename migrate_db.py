#!/usr/bin/env python3
"""
Database migration script to add missing columns to existing installations
"""
import sys
import os
sys.path.append('/opt/stoutRequests')

from app.core.database import engine
from sqlmodel import text, Session

def migrate_database():
    """Add missing columns to existing database"""
    print("🔄 Checking database schema and applying migrations...")
    
    try:
        with Session(engine) as session:
            print("📊 Connected to database")
            
            # Check and add is_server_owner column to user table
            try:
                # Try to select the column to see if it exists
                result = session.exec(text('SELECT is_server_owner FROM "user" LIMIT 1'))
                print("   ✅ is_server_owner column already exists in user table")
            except Exception:
                # Column doesn't exist, rollback current transaction and start fresh
                session.rollback()
                print("   ➕ Adding is_server_owner column to user table...")
                session.exec(text('ALTER TABLE "user" ADD COLUMN is_server_owner BOOLEAN DEFAULT FALSE'))
                session.commit()
                print("   ✅ Added is_server_owner column to user table")
            
            # Mark the first admin user as server owner
            try:
                print("   🔍 Looking for first admin user to mark as server owner...")
                result = session.exec(text("""
                    SELECT id, username FROM "user" 
                    WHERE is_admin = TRUE 
                    ORDER BY id ASC 
                    LIMIT 1
                """))
                first_admin = result.first()
                
                if first_admin:
                    user_id, username = first_admin
                    print(f"   👑 Found first admin user: {username} (ID: {user_id})")
                    
                    # Update them to be server owner
                    session.exec(text("""
                        UPDATE "user" 
                        SET is_server_owner = TRUE 
                        WHERE id = :user_id
                    """), {"user_id": user_id})
                    session.commit()
                    print(f"   ✅ Marked {username} as server owner")
                else:
                    print("   ℹ️  No admin users found - server owner will be set during next admin creation")
            except Exception as e:
                print(f"   ⚠️  Could not update server owner: {e}")
            
            print("💾 Database migration completed successfully!")
            
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = migrate_database()
    if success:
        print("\n🎉 Migration complete! You can now restart the server.")
        print("🚀 The first admin user is now the permanent server owner.")
    else:
        print("\n❌ Migration failed. Please check the errors above.")
        sys.exit(1)