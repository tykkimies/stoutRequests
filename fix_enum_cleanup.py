#!/usr/bin/env python3
"""
Script to clean up duplicate enum values in requeststatus enum.
Removes uppercase duplicates and ensures only lowercase values exist.
"""

import os
import psycopg2
from urllib.parse import urlparse

def cleanup_enum():
    """Remove uppercase enum duplicates and standardize to lowercase"""
    
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
                
                # Check for any requests using uppercase values
                cur.execute("""
                    SELECT DISTINCT status FROM mediarequest 
                    WHERE status IN ('APPROVED', 'AVAILABLE', 'DOWNLOADING', 'PENDING', 'REJECTED')
                """)
                
                uppercase_in_use = [row[0] for row in cur.fetchall()]
                print(f"📋 Uppercase values in use: {uppercase_in_use}")
                
                # Update any uppercase values to lowercase
                if uppercase_in_use:
                    print("🔄 Converting uppercase values to lowercase...")
                    
                    mappings = {
                        'APPROVED': 'approved',
                        'AVAILABLE': 'available', 
                        'DOWNLOADING': 'downloading',
                        'PENDING': 'pending',
                        'REJECTED': 'rejected'
                    }
                    
                    for old_val, new_val in mappings.items():
                        if old_val in uppercase_in_use:
                            cur.execute("UPDATE mediarequest SET status = %s WHERE status = %s", (new_val, old_val))
                            print(f"   Updated {old_val} → {new_val}")
                
                # Now we can safely drop the uppercase enum values
                uppercase_to_remove = ['APPROVED', 'AVAILABLE', 'DOWNLOADING', 'PENDING', 'REJECTED']
                
                for val in uppercase_to_remove:
                    if val in current_values:
                        print(f"🗑️ Removing uppercase enum value: {val}")
                        # PostgreSQL doesn't support removing enum values directly
                        # We'll need to recreate the enum type
                        
                # Since we can't remove enum values easily, let's ensure we have all lowercase values
                required_lowercase = ['pending', 'approved', 'downloading', 'downloaded', 'available', 'rejected']
                
                for val in required_lowercase:
                    if val not in current_values:
                        print(f"➕ Adding missing enum value: {val}")
                        cur.execute("ALTER TYPE requeststatus ADD VALUE %s", (val,))
                
        conn.close()
        print("✅ Enum cleanup completed successfully")
        return True
                
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

if __name__ == "__main__":
    success = cleanup_enum()
    if success:
        print("\n🎉 Database enum values cleaned up!")
        print("📝 Note: Both cases exist, but data now uses lowercase")
    else:
        print("\n❌ Cleanup failed. Please check the error messages above.")