#!/usr/bin/env python3
"""
Migration script to create the enhanced permissions system tables
"""
import sys
import os
sys.path.append('/opt/stoutRequests')

from app.core.database import engine
from sqlmodel import text, Session, SQLModel
from app.models.role import Role
from app.models.user_permissions import UserPermissions
from app.services.permissions_service import PermissionsService

def create_permissions_tables():
    """Create the permissions system tables"""
    print("🔄 Creating enhanced permissions system tables...")
    
    try:
        # Create all tables using SQLModel
        print("   📋 Creating tables using SQLModel...")
        SQLModel.metadata.create_all(engine)
        print("   ✅ Tables created successfully")
        
        with Session(engine) as session:
            print("📊 Connected to database")
            
            # Ensure default roles are created
            print("   🏷️  Creating default roles...")
            PermissionsService.ensure_default_roles(session)
            print("   ✅ Default roles created")
            
            # Migrate existing admin users
            print("   👥 Migrating existing admin users...")
            
            # Get all admin users
            admin_users_result = session.exec(text("""
                SELECT id, username, is_admin 
                FROM "user" 
                WHERE is_admin = TRUE
            """))
            
            admin_users = admin_users_result.all()
            
            if admin_users:
                # Get admin role
                admin_role_result = session.exec(text("SELECT id FROM role WHERE name = 'admin'"))
                admin_role = admin_role_result.first()
                
                if admin_role:
                    admin_role_id = admin_role[0]
                    
                    for user_id, username, is_admin in admin_users:
                        # Check if user permissions already exist
                        stmt = text(f"SELECT user_id FROM userpermissions WHERE user_id = {user_id}")
                        existing_perms = session.exec(stmt).first()
                        
                        if not existing_perms:
                            # Create user permissions
                            stmt = text(f"""
                                INSERT INTO userpermissions (user_id, role_id, created_at, updated_at)
                                VALUES ({user_id}, {admin_role_id}, NOW(), NOW())
                            """)
                            session.exec(stmt)
                            
                            print(f"   ✅ Assigned admin role to: {username}")
            
            # Assign default roles to all other users
            print("   🔄 Assigning default roles to other users...")
            
            # Get default role
            default_role_result = session.exec(text("SELECT id FROM role WHERE is_default = TRUE"))
            default_role = default_role_result.first()
            
            if default_role:
                default_role_id = default_role[0]
                
                # Get all non-admin users without permissions
                regular_users_result = session.exec(text("""
                    SELECT u.id, u.username 
                    FROM "user" u 
                    LEFT JOIN userpermissions up ON u.id = up.user_id 
                    WHERE u.is_admin = FALSE AND up.user_id IS NULL
                """))
                
                regular_users = regular_users_result.all()
                
                for user_id, username in regular_users:
                    stmt = text(f"""
                        INSERT INTO userpermissions (user_id, role_id, created_at, updated_at)
                        VALUES ({user_id}, {default_role_id}, NOW(), NOW())
                    """)
                    session.exec(stmt)
                    
                    print(f"   ✅ Assigned default role to: {username}")
            
            session.commit()
            print("💾 Permissions tables created and populated successfully!")
            
    except Exception as e:
        print(f"❌ Error creating permissions tables: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = create_permissions_tables()
    if success:
        print("\n🎉 Enhanced permissions system created successfully!")
        print("🚀 Database now has role and user_permissions tables.")
        print("📋 Default roles: Administrator, Moderator, Power User, Basic User, Limited User")
    else:
        print("\n❌ Failed to create permissions system. Please check the errors above.")
        sys.exit(1)