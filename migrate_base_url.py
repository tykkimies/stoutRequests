#!/usr/bin/env python3
"""
Migration script to add base_url field to settings table for reverse proxy support.
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# Add the app directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Add base_url field to settings table if it doesn't exist"""
    # Get database URL from environment or use default
    database_url = os.getenv('DATABASE_URL', 'postgresql://stout:password@localhost/stout_requests')
    
    print(f"🔗 Connecting to database...")
    engine = create_engine(database_url)
    
    try:
        with engine.connect() as conn:
            # Check if base_url column exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'settings' AND column_name = 'base_url'
            """))
            
            if result.fetchone():
                print("ℹ️  base_url column already exists in settings table")
                return
            
            # Add base_url column
            print("➕ Adding base_url column to settings table...")
            conn.execute(text("""
                ALTER TABLE settings 
                ADD COLUMN base_url VARCHAR(200) NOT NULL DEFAULT ''
            """))
            
            # Commit the changes
            conn.commit()
            print("✅ Successfully added base_url column to settings table")
            
            # Add helpful comment
            conn.execute(text("""
                COMMENT ON COLUMN settings.base_url IS 'Base URL for reverse proxy support (e.g., "/stout")'
            """))
            conn.commit()
            print("📝 Added column comment")
            
    except OperationalError as e:
        if 'already exists' in str(e).lower():
            print("ℹ️  base_url column already exists")
        else:
            print(f"❌ Database error: {e}")
            return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1
    
    print("🎉 Migration completed successfully!")
    print("\n📋 Next steps:")
    print("1. Restart your Stout Requests application")
    print("2. Go to Admin > General Settings")
    print("3. Configure the Base URL for your reverse proxy setup")
    print("   - Example: '/stout' for nginx proxy_pass /stout/")
    print("   - Leave empty if not using a reverse proxy")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())