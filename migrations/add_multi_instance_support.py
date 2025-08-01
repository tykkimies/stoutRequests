"""
Migration to add multi-instance support enhancements
Adds fields for:
- ServiceInstance: is_default_movie, is_default_tv, is_4k_default, instance_category, quality_tier
- UserPermissions: instance_permissions JSON field
- MediaRequest: service_instance_id, requested_quality_tier
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine

def run_migration():
    """Run the migration to add multi-instance support fields"""
    print("🔄 Running migration: add_multi_instance_support")
    
    with engine.connect() as connection:
        
        # ServiceInstance table updates
        print("📝 Updating serviceinstance table...")
        
        # Add multi-instance configuration fields
        service_instance_fields = [
            ("is_default_movie", "BOOLEAN DEFAULT FALSE"),
            ("is_default_tv", "BOOLEAN DEFAULT FALSE"), 
            ("is_4k_default", "BOOLEAN DEFAULT FALSE"),
            ("instance_category", "VARCHAR(50)"),
            ("quality_tier", "VARCHAR(20) DEFAULT 'standard'")
        ]
        
        for field_name, field_type in service_instance_fields:
            try:
                connection.execute(text(f"ALTER TABLE serviceinstance ADD COLUMN {field_name} {field_type}"))
                print(f"✅ Added {field_name} column to serviceinstance")
            except Exception as e:
                if "already exists" in str(e) or "duplicate column" in str(e).lower():
                    print(f"⚠️ {field_name} column already exists in serviceinstance")
                else:
                    print(f"❌ Error adding {field_name} column to serviceinstance: {e}")
                    raise
        
        # UserPermissions table updates
        print("📝 Updating userpermissions table...")
        
        # Add instance permissions JSON field
        try:
            connection.execute(text("ALTER TABLE userpermissions ADD COLUMN instance_permissions VARCHAR(2000)"))
            print("✅ Added instance_permissions column to userpermissions")
        except Exception as e:
            if "already exists" in str(e) or "duplicate column" in str(e).lower():
                print("⚠️ instance_permissions column already exists in userpermissions")
            else:
                print(f"❌ Error adding instance_permissions column to userpermissions: {e}")
                raise
        
        # MediaRequest table updates  
        print("📝 Updating mediarequest table...")
        
        # Add multi-instance support fields
        media_request_fields = [
            ("service_instance_id", "INTEGER REFERENCES serviceinstance(id)"),
            ("requested_quality_tier", "VARCHAR(20) DEFAULT 'standard'")
        ]
        
        for field_name, field_type in media_request_fields:
            try:
                connection.execute(text(f"ALTER TABLE mediarequest ADD COLUMN {field_name} {field_type}"))
                print(f"✅ Added {field_name} column to mediarequest")
            except Exception as e:
                if "already exists" in str(e) or "duplicate column" in str(e).lower():
                    print(f"⚠️ {field_name} column already exists in mediarequest")
                else:
                    print(f"❌ Error adding {field_name} column to mediarequest: {e}")
                    raise
        
        # Data migration for backward compatibility
        print("📝 Performing data migration for backward compatibility...")
        
        try:
            # Set default quality_tier for existing service instances 
            result = connection.execute(text("UPDATE serviceinstance SET quality_tier = 'standard' WHERE quality_tier IS NULL"))
            print(f"✅ Updated {result.rowcount} serviceinstance records with default quality_tier")
        except Exception as e:
            print(f"⚠️ Warning updating serviceinstance default values: {e}")
        
        try:
            # Set default requested_quality_tier for existing media requests
            result = connection.execute(text("UPDATE mediarequest SET requested_quality_tier = 'standard' WHERE requested_quality_tier IS NULL"))
            print(f"✅ Updated {result.rowcount} mediarequest records with default requested_quality_tier")
        except Exception as e:
            print(f"⚠️ Warning updating mediarequest default values: {e}")
        
        # Migration for legacy 4K permissions
        print("📝 Migrating legacy 4K permissions...")
        
        try:
            # Find users with can_request_4k = true and create instance permissions
            result = connection.execute(text("""
                UPDATE userpermissions 
                SET instance_permissions = '{"category_4k": true}' 
                WHERE can_request_4k = true AND (instance_permissions IS NULL OR instance_permissions = '')
            """))
            print(f"✅ Migrated {result.rowcount} user 4K permissions to new system")
        except Exception as e:
            print(f"⚠️ Warning migrating 4K permissions: {e}")
        
        # Commit all changes
        connection.commit()
    
    print("✅ Migration completed: multi-instance support added successfully")
    print("")
    print("📋 Next steps:")
    print("1. Configure default instances using the admin interface")
    print("2. Set instance categories (4k, anime, etc.) as needed")
    print("3. Assign instance permissions to users")
    print("4. Test request creation with instance selection")

if __name__ == "__main__":
    run_migration()