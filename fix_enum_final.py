#!/usr/bin/env python3
"""
Final enum fix - recreate the enum type with only lowercase values
"""

import os
import psycopg2
from urllib.parse import urlparse

def fix_enum_final():
    """Recreate requeststatus enum with only lowercase values"""
    
    database_url = os.getenv('DATABASE_URL', 'postgresql://stout:Yyxd7fku!@localhost/stout_requests')
    print(f"🔄 Connecting to database...")
    
    try:
        parsed = urlparse(database_url)
        
        conn = psycopg2.connect(
            host=parsed.hostname or 'localhost',
            port=parsed.port or 5432,
            database=parsed.path[1:] if parsed.path else 'stout_requests',
            user=parsed.username,
            password=parsed.password
        )
        
        with conn:
            with conn.cursor() as cur:
                print("🔄 Creating new enum type with only lowercase values...")
                
                # Create new enum type with only lowercase values
                cur.execute("""
                    CREATE TYPE requeststatus_new AS ENUM (
                        'pending', 'approved', 'downloading', 'downloaded', 'available', 'rejected'
                    );
                """)
                
                # Update the table to use the new enum type
                print("🔄 Updating table to use new enum...")
                cur.execute("""
                    ALTER TABLE mediarequest 
                    ALTER COLUMN status TYPE requeststatus_new 
                    USING status::text::requeststatus_new;
                """)
                
                # Drop old enum type
                print("🗑️ Dropping old enum type...")
                cur.execute("DROP TYPE requeststatus;")
                
                # Rename new enum type
                print("🔄 Renaming new enum type...")
                cur.execute("ALTER TYPE requeststatus_new RENAME TO requeststatus;")
                
        conn.close()
        print("✅ Enum recreation completed successfully")
        return True
                
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

if __name__ == "__main__":
    success = fix_enum_final()
    if success:
        print("\n🎉 Database enum type recreated with lowercase values only!")
    else:
        print("\n❌ Recreation failed. Please check the error messages above.")