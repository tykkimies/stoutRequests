#!/usr/bin/env python3
"""
Migration script to create roles and user_permissions tables and set up default roles.
"""

import os
import sys
import json
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# Add the app directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Create roles system tables and initialize default roles"""
    # Get database URL from environment or use default
    database_url = os.getenv('DATABASE_URL', 'postgresql://stout:Yyxd7fku!@localhost/stout_requests')
    
    print(f"🔗 Connecting to database...")
    engine = create_engine(database_url)
    
    try:
        with engine.connect() as conn:
            # Check if roles table already exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'role'
                );
            """))
            roles_table_exists = result.fetchone()[0]
            
            if not roles_table_exists:
                print("📋 Creating roles table...")
                
                # Create the roles table
                conn.execute(text("""
                    CREATE TABLE role (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(50) NOT NULL UNIQUE,
                        display_name VARCHAR(100) NOT NULL,
                        description VARCHAR(500),
                        permissions TEXT NOT NULL DEFAULT '{}',
                        is_default BOOLEAN NOT NULL DEFAULT FALSE,
                        is_system BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP WITHOUT TIME ZONE
                    );
                """))
                
                # Create indexes
                conn.execute(text("""
                    CREATE INDEX ix_role_name ON role (name);
                    CREATE INDEX ix_role_is_default ON role (is_default);
                    CREATE INDEX ix_role_is_system ON role (is_system);
                """))
                
                print("✅ Roles table created successfully!")
            else:
                print("✅ Roles table already exists.")
            
            # Check if user_permissions table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'user_permissions'
                );
            """))
            user_permissions_table_exists = result.fetchone()[0]
            
            if not user_permissions_table_exists:
                print("📋 Creating user_permissions table...")
                
                # Create the user_permissions table
                conn.execute(text("""
                    CREATE TABLE user_permissions (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                        role_id INTEGER REFERENCES role(id) ON DELETE SET NULL,
                        custom_permissions TEXT DEFAULT '{}',
                        max_requests INTEGER,
                        request_retention_days INTEGER,
                        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP WITHOUT TIME ZONE,
                        UNIQUE(user_id)
                    );
                """))
                
                # Create indexes
                conn.execute(text("""
                    CREATE INDEX ix_user_permissions_user_id ON user_permissions (user_id);
                    CREATE INDEX ix_user_permissions_role_id ON user_permissions (role_id);
                """))
                
                print("✅ User permissions table created successfully!")
            else:
                print("✅ User permissions table already exists.")
            
            # Initialize default roles
            print("🔄 Setting up default roles...")
            
            # Define basic permission sets (simplified for migration)
            admin_permissions = {
                "admin.full": True,
                "admin.manage_users": True,
                "admin.manage_settings": True,
                "admin.approve_requests": True,
                "admin.delete_requests": True,
                "request.movies": True,
                "request.tv": True,
                "request.4k": True,
                "request.unlimited": True,
                "request.view_all": True
            }
            
            moderator_permissions = {
                "admin.approve_requests": True,
                "admin.view_all_requests": True,
                "request.movies": True,
                "request.tv": True,
                "request.4k": True,
                "request.view_all": True,
                "request.manage_all": True
            }
            
            power_user_permissions = {
                "request.movies": True,
                "request.tv": True,
                "request.4k": True,
                "request.auto_approve.movies": True,
                "request.auto_approve.tv": True,
                "request.view_all": True
            }
            
            basic_user_permissions = {
                "request.movies": True,
                "request.tv": True,
                "request.manage_own": True
            }
            
            default_roles = [
                {
                    'name': 'administrator',
                    'display_name': 'Administrator',
                    'description': 'Full administrative access to all features',
                    'permissions': json.dumps(admin_permissions),
                    'is_system': True,
                    'is_default': False
                },
                {
                    'name': 'moderator',
                    'display_name': 'Moderator',
                    'description': 'Can manage requests and moderate content with limited admin access',
                    'permissions': json.dumps(moderator_permissions),
                    'is_system': True,
                    'is_default': False
                },
                {
                    'name': 'power_user',
                    'display_name': 'Power User',
                    'description': 'Advanced user with auto-approval and 4K access',
                    'permissions': json.dumps(power_user_permissions),
                    'is_system': True,
                    'is_default': False
                },
                {
                    'name': 'basic_user',
                    'display_name': 'Basic User',
                    'description': 'Standard user with basic request privileges',
                    'permissions': json.dumps(basic_user_permissions),
                    'is_system': True,
                    'is_default': True
                }
            ]
            
            # Insert roles if they don't exist
            for role_data in default_roles:
                result = conn.execute(text("""
                    SELECT id FROM role WHERE name = :name;
                """), {'name': role_data['name']})
                
                if not result.fetchone():
                    conn.execute(text("""
                        INSERT INTO role (name, display_name, description, permissions, is_system, is_default, created_at)
                        VALUES (:name, :display_name, :description, :permissions, :is_system, :is_default, NOW());
                    """), role_data)
                    print(f"  ✅ Created role: {role_data['display_name']}")
                else:
                    print(f"  ℹ️ Role already exists: {role_data['display_name']}")
            
            conn.commit()
            print("✅ Default roles setup completed!")
            
            # Assign administrator role to first admin user if they don't have a role
            print("🔄 Checking first admin user role assignment...")
            
            result = conn.execute(text("""
                SELECT u.id, u.username, u.is_admin
                FROM "user" u
                LEFT JOIN user_permissions up ON u.id = up.user_id
                WHERE u.is_admin = true AND up.role_id IS NULL
                ORDER BY u.id ASC
                LIMIT 1;
            """))
            
            first_admin = result.fetchone()
            
            if first_admin:
                user_id, username, is_admin = first_admin
                print(f"📝 Found admin user without role: {username} (ID: {user_id})")
                
                # Get administrator role ID
                result = conn.execute(text("""
                    SELECT id FROM role WHERE name = 'administrator' LIMIT 1;
                """))
                admin_role = result.fetchone()
                
                if admin_role:
                    admin_role_id = admin_role[0]
                    
                    # Assign administrator role to this user
                    conn.execute(text("""
                        INSERT INTO user_permissions (user_id, role_id)
                        VALUES (:user_id, :role_id)
                        ON CONFLICT (user_id) DO UPDATE SET role_id = :role_id;
                    """), {
                        'user_id': user_id,
                        'role_id': admin_role_id
                    })
                    
                    conn.commit()
                    print(f"✅ Assigned Administrator role to user: {username}")
                else:
                    print("⚠️ Administrator role not found!")
            else:
                print("ℹ️ No admin users without roles found.")
            
            print("🎉 Roles system migration completed successfully!")
            
    except OperationalError as e:
        print(f"❌ Database operation failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()