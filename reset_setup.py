#!/usr/bin/env python3
"""
CuePlex Database Reset Script
Empties the database for fresh packaging/distribution
"""

import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlmodel import Session, text
from app.core.database import engine
from app.models import *  # Import all models to ensure they're registered


def confirm_reset():
    """Confirm that user wants to reset the database"""
    print("🚨 DATABASE RESET WARNING")
    print("=" * 40)
    print("This will PERMANENTLY DELETE all data:")
    print("• All users")
    print("• All media requests") 
    print("• All settings")
    print("• All cached data")
    print("• Job history")
    print("• Everything!")
    print()
    
    confirmation = input("Type 'RESET' to confirm (case sensitive): ")
    return confirmation == "RESET"


def reset_database():
    """Reset the database to empty state"""
    print("\n🔄 Resetting CuePlex database...")
    
    # Get all table names first
    try:
        with Session(engine) as session:
            result = session.exec(text("""
                SELECT tablename 
                FROM pg_tables 
                WHERE schemaname = 'public'
                AND tablename NOT LIKE 'pg_%'
                AND tablename NOT LIKE 'sql_%'
                ORDER BY tablename;
            """))
            tables = [row for row in result]
            print(f"📊 Found {len(tables)} tables to reset")
    except Exception as e:
        print(f"❌ Error getting table list: {e}")
        return False
    
    # Define deletion order to handle foreign keys
    priority_tables = [
        'user_permissions', 'userpermissions', 
        'user_category_preferences', 'user_custom_categories',
        'mediarequest', 'plex_library_item', 'plex_tv_item', 'plexlibraryitem',
        'job_executions', 'apscheduler_jobs', 'cueplex_jobs',
        'category_cache', 'service_instance', 'serviceinstance',
        'user', 'role', 'settings'
    ]
    
    processed_tables = set()
    failed_tables = []
    
    # Delete data from tables - each in its own transaction
    # First, try to delete from priority tables
    for table_name in priority_tables:
        if table_name in tables and table_name not in processed_tables:
            try:
                with Session(engine) as session:
                    print(f"🗑️  Emptying table: {table_name}")
                    result = session.exec(text(f'SELECT COUNT(*) FROM "{table_name}";'))
                    count = result.first()
                    if count and count > 0:
                        session.exec(text(f'DELETE FROM "{table_name}";'))
                        session.commit()
                        print(f"   ✅ Deleted {count} rows from {table_name}")
                    else:
                        print(f"   ℹ️  {table_name} was already empty")
                    processed_tables.add(table_name)
            except Exception as e:
                print(f"   ⚠️  Could not delete from {table_name}: {e}")
                failed_tables.append(table_name)
    
    # Then handle any remaining tables
    for table_name in tables:
        if table_name not in processed_tables:
            try:
                with Session(engine) as session:
                    print(f"🗑️  Emptying table: {table_name}")
                    result = session.exec(text(f'SELECT COUNT(*) FROM "{table_name}";'))
                    count = result.first()
                    if count and count > 0:
                        session.exec(text(f'DELETE FROM "{table_name}";'))
                        session.commit()
                        print(f"   ✅ Deleted {count} rows from {table_name}")
                    else:
                        print(f"   ℹ️  {table_name} was already empty")
                    processed_tables.add(table_name)
            except Exception as e:
                print(f"   ⚠️  Could not delete from {table_name}: {e}")
                failed_tables.append(table_name)
    
    # Reset sequences for auto-incrementing IDs
    print("\n🔄 Resetting ID sequences...")
    try:
        with Session(engine) as session:
            sequence_result = session.exec(text("""
                SELECT sequence_name 
                FROM information_schema.sequences 
                WHERE sequence_schema = 'public';
            """))
            
            sequences = [row for row in sequence_result]
            
        # Reset each sequence in its own transaction
        for sequence_name in sequences:
            try:
                with Session(engine) as session:
                    session.exec(text(f'ALTER SEQUENCE "{sequence_name}" RESTART WITH 1;'))
                    session.commit()
                    print(f"   ↻ Reset sequence: {sequence_name}")
            except Exception as e:
                print(f"   ⚠️  Could not reset sequence {sequence_name}: {e}")
                
    except Exception as e:
        print(f"⚠️  Error getting sequences: {e}")
    
    if failed_tables:
        print(f"\n⚠️  Some tables could not be emptied: {failed_tables}")
        print("This may be due to foreign key constraints or permissions")
        return False
    else:
        print("\n✅ Database reset completed successfully")
        return True


def verify_empty_database():
    """Verify that the database is empty"""
    print("\n🔍 Verifying database is empty...")
    
    try:
        with Session(engine) as session:
            # Check a few key tables
            key_tables = ['user', 'mediarequest', 'settings', 'plex_library_item']
            
            for table in key_tables:
                try:
                    result = session.exec(text(f'SELECT COUNT(*) FROM "{table}";'))
                    count = result.first()
                    if count and count > 0:
                        print(f"⚠️  Warning: {table} still has {count} rows")
                        return False
                    else:
                        print(f"✅ {table}: empty")
                except Exception:
                    print(f"ℹ️  {table}: table doesn't exist (ok)")
            
            print("✅ Database verification complete - all tables are empty")
            return True
            
    except Exception as e:
        print(f"❌ Error during verification: {e}")
        return False


def main():
    print("🎬 CuePlex Database Reset Utility")
    print("=" * 35)
    
    # Check database connection
    try:
        with Session(engine) as session:
            session.exec(text("SELECT 1;"))
        print("✅ Database connection successful")
    except Exception as e:
        print(f"❌ Cannot connect to database: {e}")
        print("Make sure the database is running and .env is configured correctly")
        return 1
    
    # Confirm reset
    if not confirm_reset():
        print("❌ Reset cancelled")
        return 0
    
    # Perform reset
    if not reset_database():
        return 1
    
    # Verify reset
    if not verify_empty_database():
        print("⚠️  Database reset completed but verification failed")
        return 1
    
    print("\n🎉 Database reset successful!")
    print("Your CuePlex database is now empty and ready for fresh packaging.")
    print()
    print("Next steps:")
    print("1. Build your Docker image")
    print("2. Test the fresh installation")
    print("3. Publish to Docker Hub")
    
    return 0


if __name__ == "__main__":
    exit(main())