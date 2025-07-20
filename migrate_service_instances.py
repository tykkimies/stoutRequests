#!/usr/bin/env python3
"""
Migration script to create service_instance table for multiple Radarr/Sonarr instances.
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# Add the app directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Create service_instance table if it doesn't exist"""
    # Get database URL from environment or use default
    database_url = os.getenv('DATABASE_URL', 'postgresql://stout:Yyxd7fku!@localhost/stout_requests')
    
    print(f"🔗 Connecting to database...")
    engine = create_engine(database_url)
    
    try:
        with engine.connect() as conn:
            # Check if service_instance table already exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'service_instance'
                );
            """))
            table_exists = result.fetchone()[0]
            
            if table_exists:
                print("✅ service_instance table already exists. No migration needed.")
                return
            
            print("📋 Creating service_instance table...")
            
            # Create the service_instance table
            conn.execute(text("""
                CREATE TABLE service_instance (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    service_type VARCHAR NOT NULL,
                    hostname VARCHAR NOT NULL,
                    port INTEGER NOT NULL DEFAULT 7878,
                    use_ssl BOOLEAN NOT NULL DEFAULT FALSE,
                    api_key VARCHAR NOT NULL,
                    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    is_default BOOLEAN NOT NULL DEFAULT FALSE,
                    root_folder VARCHAR,
                    quality_profile_id INTEGER,
                    language_profile_id INTEGER,
                    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITHOUT TIME ZONE
                );
            """))
            
            # Create indexes
            conn.execute(text("""
                CREATE INDEX ix_service_instance_service_type ON service_instance (service_type);
                CREATE INDEX ix_service_instance_is_enabled ON service_instance (is_enabled);
                CREATE INDEX ix_service_instance_is_default ON service_instance (is_default);
            """))
            
            # Add check constraint for service_type
            conn.execute(text("""
                ALTER TABLE service_instance 
                ADD CONSTRAINT service_instance_service_type_check 
                CHECK (service_type IN ('RADARR', 'SONARR'));
            """))
            
            conn.commit()
            print("✅ service_instance table created successfully!")
            
            # Migrate existing Radarr/Sonarr settings from the settings table if they exist
            print("🔄 Checking for existing Radarr/Sonarr settings to migrate...")
            
            # Check if there are existing radarr/sonarr settings
            result = conn.execute(text("""
                SELECT radarr_url, radarr_api_key, sonarr_url, sonarr_api_key 
                FROM settings 
                WHERE (radarr_url IS NOT NULL AND radarr_url != '') 
                   OR (sonarr_url IS NOT NULL AND sonarr_url != '') 
                LIMIT 1;
            """))
            
            existing_settings = result.fetchone()
            
            if existing_settings:
                radarr_url, radarr_api_key, sonarr_url, sonarr_api_key = existing_settings
                
                # Migrate Radarr settings
                if radarr_url and radarr_api_key:
                    print("📦 Migrating existing Radarr settings...")
                    # Parse URL to get hostname, port, and SSL
                    from urllib.parse import urlparse
                    parsed = urlparse(radarr_url)
                    hostname = parsed.hostname or parsed.netloc.split(':')[0]
                    port = parsed.port or (443 if parsed.scheme == 'https' else 7878)
                    use_ssl = parsed.scheme == 'https'
                    
                    conn.execute(text("""
                        INSERT INTO service_instance 
                        (name, service_type, hostname, port, use_ssl, api_key, is_enabled, is_default)
                        VALUES ('Radarr (Migrated)', 'RADARR', :hostname, :port, :use_ssl, :api_key, true, true);
                    """), {
                        'hostname': hostname,
                        'port': port,
                        'use_ssl': use_ssl,
                        'api_key': radarr_api_key
                    })
                    print(f"  ✅ Migrated Radarr: {hostname}:{port} (SSL: {use_ssl})")
                
                # Migrate Sonarr settings
                if sonarr_url and sonarr_api_key:
                    print("📺 Migrating existing Sonarr settings...")
                    # Parse URL to get hostname, port, and SSL
                    from urllib.parse import urlparse
                    parsed = urlparse(sonarr_url)
                    hostname = parsed.hostname or parsed.netloc.split(':')[0]
                    port = parsed.port or (443 if parsed.scheme == 'https' else 8989)
                    use_ssl = parsed.scheme == 'https'
                    
                    conn.execute(text("""
                        INSERT INTO service_instance 
                        (name, service_type, hostname, port, use_ssl, api_key, is_enabled, is_default)
                        VALUES ('Sonarr (Migrated)', 'SONARR', :hostname, :port, :use_ssl, :api_key, true, true);
                    """), {
                        'hostname': hostname,
                        'port': port,
                        'use_ssl': use_ssl,
                        'api_key': sonarr_api_key
                    })
                    print(f"  ✅ Migrated Sonarr: {hostname}:{port} (SSL: {use_ssl})")
                
                conn.commit()
                print("✅ Migration of existing service settings complete!")
            else:
                print("ℹ️ No existing Radarr/Sonarr settings found to migrate.")
            
    except OperationalError as e:
        print(f"❌ Database operation failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()