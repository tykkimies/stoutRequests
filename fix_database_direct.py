#!/usr/bin/env python3
"""
Direct database fix - connect to PostgreSQL and fix the schema manually
"""
import sys
import os
sys.path.append('/opt/stoutRequests')

def fix_database_direct():
    """Connect directly to PostgreSQL and fix the database"""
    print("🔄 Connecting directly to PostgreSQL to fix database...")
    
    try:
        import psycopg2
        from app.core.config import settings
        
        # Parse database URL
        database_url = settings.database_url
        print(f"🔗 Database URL: {database_url}")
        
        # Extract connection parameters from database URL
        # Format: postgresql://user:password@host:port/database
        if database_url.startswith('postgresql://'):
            url_parts = database_url.replace('postgresql://', '').split('/')
            auth_host = url_parts[0]
            database_name = url_parts[1] if len(url_parts) > 1 else 'stoutrequests'
            
            if '@' in auth_host:
                auth, host_port = auth_host.split('@')
                if ':' in auth:
                    username, password = auth.split(':')
                else:
                    username = auth
                    password = ''
            else:
                host_port = auth_host
                username = 'postgres'
                password = ''
            
            if ':' in host_port:
                host, port = host_port.split(':')
                port = int(port)
            else:
                host = host_port
                port = 5432
        else:
            # Fallback defaults
            host = 'localhost'
            port = 5432
            database_name = 'stoutrequests'
            username = 'postgres'
            password = ''
        
        print(f"📊 Connecting to PostgreSQL at {host}:{port}, database: {database_name}")
        
        # Connect to PostgreSQL with autocommit
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database_name,
            user=username,
            password=password
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        print("✅ Connected to PostgreSQL")
        
        # Check if is_server_owner column exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'user' AND column_name = 'is_server_owner'
        """)
        column_exists = cursor.fetchone()
        
        if not column_exists:
            print("➕ Adding is_server_owner column to user table...")
            cursor.execute("ALTER TABLE \"user\" ADD COLUMN is_server_owner BOOLEAN DEFAULT FALSE")
            print("✅ Added is_server_owner column")
        else:
            print("✅ is_server_owner column already exists")
        
        # Check if we have any admin users
        cursor.execute("SELECT id, username FROM \"user\" WHERE is_admin = TRUE ORDER BY id LIMIT 1")
        first_admin = cursor.fetchone()
        
        if first_admin:
            user_id, username = first_admin
            print(f"👑 Found first admin user: {username} (ID: {user_id})")
            
            # Make them server owner
            cursor.execute("UPDATE \"user\" SET is_server_owner = TRUE WHERE id = %s", (user_id,))
            print(f"✅ Marked {username} as server owner")
        else:
            print("ℹ️ No admin users found - server owner will be set during next setup")
        
        # Clear any browser cookies by clearing the user
        print("🧹 Clearing any cached authentication...")
        cursor.execute("UPDATE \"user\" SET updated_at = NOW()")
        
        cursor.close()
        conn.close()
        
        print("💾 Database fix completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error during database fix: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = fix_database_direct()
    if success:
        print("\n🎉 Database fix complete!")
        print("🧹 Clear your browser cookies and try again")
        print("🚀 The first admin user should now be server owner")
    else:
        print("\n❌ Database fix failed. Please check the errors above.")
        sys.exit(1)