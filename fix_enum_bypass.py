#!/usr/bin/env python3
"""
Fix enum issue by updating all status values to use string literals
"""

import os
import psycopg2
from urllib.parse import urlparse

def update_enum_values_to_uppercase():
    """Update database enum values to uppercase to match SQLAlchemy expectations"""
    
    database_url = os.getenv('DATABASE_URL', 'postgresql://stout:Yyxd7fku!@localhost/stout_requests')
    print(f"🔄 Updating enum values to uppercase...")
    
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
                print("🔄 Creating new enum with uppercase values...")
                
                # Create new enum with uppercase values to match SQLAlchemy
                cur.execute("""
                    CREATE TYPE requeststatus_upper AS ENUM (
                        'PENDING', 'APPROVED', 'AVAILABLE', 'REJECTED'
                    );
                """)
                
                # Update table to use new enum with data conversion
                print("🔄 Updating table schema and converting data...")
                cur.execute("""
                    ALTER TABLE mediarequest 
                    ALTER COLUMN status TYPE requeststatus_upper 
                    USING UPPER(status::text)::requeststatus_upper;
                """)
                
                # Drop old enum
                cur.execute("DROP TYPE requeststatus;")
                
                # Rename new enum
                cur.execute("ALTER TYPE requeststatus_upper RENAME TO requeststatus;")
                
                print("✅ Enum updated to uppercase values")
                
                # Verify final state
                cur.execute("""
                    SELECT enumlabel FROM pg_enum 
                    WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'requeststatus')
                    ORDER BY enumsortorder;
                """)
                
                final_values = [row[0] for row in cur.fetchall()]
                print(f"✅ Final enum values: {final_values}")
                
                # Check data
                cur.execute("SELECT status, COUNT(*) FROM mediarequest GROUP BY status ORDER BY status;")
                status_counts = cur.fetchall()
                print("📊 Request counts by status:")
                for status, count in status_counts:
                    print(f"   {status}: {count}")
        
        conn.close()
        print("\n✅ Database updated to uppercase enum values!")
        return True
                
    except Exception as e:
        print(f"❌ Database update error: {e}")
        return False

if __name__ == "__main__":
    success = update_enum_values_to_uppercase()
    if success:
        print("\n🎉 Database enum values now match SQLAlchemy expectations!")
        print("📝 Now update the Python enum to use uppercase values.")
    else:
        print("\n❌ Update failed. Please check the error messages above.")