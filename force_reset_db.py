#!/usr/bin/env python3
"""
Force reset database - drops and recreates all tables
"""
import sys
import os
sys.path.append('/opt/stoutRequests')

def force_reset_database():
    """Drop and recreate all database tables"""
    print("🔄 Force resetting database...")
    
    try:
        from sqlalchemy import create_engine, text
        from app.core.config import settings
        
        # Create engine with autocommit for DDL operations
        engine = create_engine(settings.database_url, echo=False)
        
        print("📊 Connected to database")
        
        # Get list of all tables
        with engine.connect() as conn:
            # Use autocommit for DDL operations
            conn = conn.execution_options(autocommit=True)
            
            print("🔍 Getting list of existing tables...")
            result = conn.execute(text("""
                SELECT tablename FROM pg_tables 
                WHERE schemaname = 'public'
            """))
            tables = [row[0] for row in result]
            print(f"   Found tables: {tables}")
            
            if tables:
                print("🗑️ Dropping all existing tables...")
                for table in tables:
                    print(f"   Dropping table: {table}")
                    conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
                print("   ✅ All tables dropped")
            else:
                print("   ℹ️ No tables found to drop")
        
        print("🔨 Creating fresh database schema...")
        
        # Now create all tables fresh
        from app.core.database import create_db_and_tables
        create_db_and_tables()
        print("   ✅ Database schema created")
        
        # Create default roles
        print("🔐 Creating default roles...")
        from app.core.database import engine as app_engine
        from sqlmodel import Session
        from app.services.permissions_service import PermissionsService
        
        with Session(app_engine) as session:
            PermissionsService.ensure_default_roles(session)
        print("   ✅ Default roles created")
        
        print("💾 Database force reset completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error during force reset: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = force_reset_database()
    if success:
        print("\n🎉 Force reset complete!")
        print("📝 You can now visit /setup to go through the setup process")
        print("🚀 Start the server and the first user will become server owner")
    else:
        print("\n❌ Force reset failed. Please check the errors above.")
        sys.exit(1)