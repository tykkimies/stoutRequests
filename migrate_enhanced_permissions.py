#!/usr/bin/env python3
"""
Migration script to enhance the permissions system with granular controls
"""
import sys
import os
sys.path.append('/opt/stoutRequests')

from app.core.database import engine
from sqlmodel import text, Session
from app.services.permissions_service import PermissionsService

def migrate_enhanced_permissions():
    """Migrate to enhanced permissions system"""
    print("🔄 Migrating to enhanced permissions system...")
    
    try:
        with Session(engine) as session:
            print("📊 Connected to database")
            
            # Ensure default roles are created/updated with new permissions
            print("   🏷️  Creating/updating default roles...")
            PermissionsService.ensure_default_roles(session)
            print("   ✅ Default roles updated with enhanced permissions")
            
            # Update existing user permissions to use new role structure
            print("   👥 Migrating existing user permissions...")
            
            # Get all users who are legacy admins but don't have roles
            admin_users_result = session.exec(text("""
                SELECT u.id, u.username, u.is_admin 
                FROM "user" u 
                LEFT JOIN user_permissions up ON u.id = up.user_id 
                WHERE u.is_admin = TRUE AND (up.role_id IS NULL OR up.role_id NOT IN (
                    SELECT id FROM role WHERE name = 'admin'
                ))
            """))
            
            admin_users = admin_users_result.all()
            
            if admin_users:
                # Get admin role
                admin_role_result = session.exec(text("SELECT id FROM role WHERE name = 'admin'"))
                admin_role = admin_role_result.first()
                
                if admin_role:
                    admin_role_id = admin_role[0]
                    
                    for user_id, username, is_admin in admin_users:
                        # Create or update user permissions
                        session.exec(text("""
                            INSERT INTO user_permissions (user_id, role_id, created_at, updated_at)
                            VALUES (:user_id, :role_id, NOW(), NOW())
                            ON CONFLICT (user_id) DO UPDATE SET 
                                role_id = :role_id,
                                updated_at = NOW()
                        """), {"user_id": user_id, "role_id": admin_role_id})
                        
                        print(f"   ✅ Assigned admin role to legacy admin: {username}")
            
            # Assign default roles to users without roles
            print("   🔄 Assigning default roles to users without roles...")
            
            # Get default role
            default_role_result = session.exec(text("SELECT id FROM role WHERE is_default = TRUE"))
            default_role = default_role_result.first()
            
            if default_role:
                default_role_id = default_role[0]
                
                # Get users without permissions records
                users_without_perms_result = session.exec(text("""
                    SELECT u.id, u.username 
                    FROM "user" u 
                    LEFT JOIN user_permissions up ON u.id = up.user_id 
                    WHERE up.user_id IS NULL
                """))
                
                users_without_perms = users_without_perms_result.all()
                
                for user_id, username in users_without_perms:
                    session.exec(text("""
                        INSERT INTO user_permissions (user_id, role_id, created_at, updated_at)
                        VALUES (:user_id, :role_id, NOW(), NOW())
                    """), {"user_id": user_id, "role_id": default_role_id})
                    
                    print(f"   ✅ Assigned default role to user: {username}")
            
            session.commit()
            print("💾 Enhanced permissions migration completed successfully!")
            
    except Exception as e:
        print(f"❌ Error during enhanced permissions migration: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = migrate_enhanced_permissions()
    if success:
        print("\n🎉 Enhanced permissions migration complete!")
        print("🚀 Users now have access to granular permission controls.")
        print("📋 New roles available: Administrator, Moderator, Power User, Basic User, Limited User")
    else:
        print("\n❌ Enhanced permissions migration failed. Please check the errors above.")
        sys.exit(1)