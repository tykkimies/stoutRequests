#!/usr/bin/env python3
"""
Migration script to add 'downloaded' enum value to requeststatus enum.
Run this to fix the database enum mismatch.
"""

import os
import psycopg2
from urllib.parse import urlparse

def fix_enum_migration():
    """Add 'downloaded' status to requeststatus enum if not present"""
    
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL', 'postgresql://stout:Yyxd7fku!@localhost/stout_requests')
    print(f"🔄 Connecting to database...")
    
    try:
        # Parse database URL
        parsed = urlparse(database_url)
        
        # Connect to database
        conn = psycopg2.connect(
            host=parsed.hostname or 'localhost',
            port=parsed.port or 5432,
            database=parsed.path[1:] if parsed.path else 'stout_requests',  # Remove leading slash
            user=parsed.username,
            password=parsed.password
        )
        
        with conn:
            with conn.cursor() as cur:
                # Check current enum values
                cur.execute("""
                    SELECT enumlabel 
                    FROM pg_enum 
                    WHERE enumtypid = (
                        SELECT oid 
                        FROM pg_type 
                        WHERE typname = 'requeststatus'
                    ) 
                    ORDER BY enumlabel;
                """)
                
                current_values = [row[0] for row in cur.fetchall()]
                print(f"📋 Current enum values: {current_values}")
                
                # Check if 'downloaded' is missing
                if 'downloaded' not in current_values:
                    print("➕ Adding 'downloaded' to requeststatus enum...")
                    
                    # Add the missing enum value
                    cur.execute("ALTER TYPE requeststatus ADD VALUE 'downloaded';")
                    
                    print("✅ Successfully added 'downloaded' enum value")
                else:
                    print("✅ 'downloaded' enum value already exists")
                
        conn.close()
        print("✅ Migration completed successfully")
        return True
                
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        print("\nTroubleshooting tips:")
        print("1. Ensure PostgreSQL is running")
        print("2. Check DATABASE_URL in .env file") 
        print("3. Verify database credentials")
        print("4. Install psycopg2: pip install psycopg2-binary")
        return False

if __name__ == "__main__":
    success = fix_enum_migration()
    if success:
        print("\n🎉 You can now restart your application!")
    else:
        print("\n❌ Migration failed. Please check the error messages above.")