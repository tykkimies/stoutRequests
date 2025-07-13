#!/usr/bin/env python3
"""
Migration script to add new columns to the settings table.
Run this script to update your database schema for the new features.
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

try:
    from core.database import engine
    from sqlmodel import text
    
    print("🔧 Starting database migration...")
    
    # Add the new columns to the existing settings table
    with engine.connect() as conn:
        try:
            # Add sync_library_preferences column
            conn.execute(text('ALTER TABLE settings ADD COLUMN sync_library_preferences VARCHAR(2000)'))
            print('✅ Added sync_library_preferences column')
        except Exception as e:
            if 'already exists' in str(e) or 'duplicate column' in str(e).lower():
                print('ℹ️  sync_library_preferences column already exists')
            else:
                print(f'⚠️  Error adding sync_library_preferences: {e}')
        
        try:
            # Add site_theme column with default value
            conn.execute(text("ALTER TABLE settings ADD COLUMN site_theme VARCHAR(50) DEFAULT 'default'"))
            print('✅ Added site_theme column')
        except Exception as e:
            if 'already exists' in str(e) or 'duplicate column' in str(e).lower():
                print('ℹ️  site_theme column already exists')
            else:
                print(f'⚠️  Error adding site_theme: {e}')
        
        # Also add new User model columns if they don't exist
        try:
            # Check if we need to update the User table as well (quote "user" since it's reserved)
            conn.execute(text('ALTER TABLE "user" ADD COLUMN password_hash VARCHAR(500)'))
            print('✅ Added password_hash column to user table')
        except Exception as e:
            if 'already exists' in str(e) or 'duplicate column' in str(e).lower():
                print('ℹ️  password_hash column already exists')
            else:
                print(f'⚠️  Error adding password_hash: {e}')
                
        try:
            conn.execute(text('ALTER TABLE "user" ADD COLUMN is_local_user BOOLEAN DEFAULT FALSE'))
            print('✅ Added is_local_user column to user table')
        except Exception as e:
            if 'already exists' in str(e) or 'duplicate column' in str(e).lower():
                print('ℹ️  is_local_user column already exists')
            else:
                print(f'⚠️  Error adding is_local_user: {e}')
        
        try:
            # Make plex_id nullable and username unique
            conn.execute(text('ALTER TABLE "user" ALTER COLUMN plex_id DROP NOT NULL'))
            print('✅ Made plex_id nullable')
        except Exception as e:
            print(f'ℹ️  plex_id nullability: {e}')
            
        try:
            # Add unique constraint to username if it doesn't exist
            conn.execute(text('ALTER TABLE "user" ADD CONSTRAINT user_username_unique UNIQUE (username)'))
            print('✅ Added unique constraint to username')
        except Exception as e:
            if 'already exists' in str(e) or 'unique' in str(e).lower():
                print('ℹ️  username unique constraint already exists')
            else:
                print(f'⚠️  Error adding username unique constraint: {e}')
        
        # Commit all changes
        conn.commit()
        print('✅ Database schema migration completed successfully!')
        print('')
        print('🎉 Your database is now ready for the new features:')
        print('   • Local User Authentication')
        print('   • Library Sync Preferences') 
        print('   • Site Theme Switching')
        
except ImportError as e:
    print(f"❌ Error importing modules: {e}")
    print("Make sure you're running this from the correct directory with the virtual environment activated.")
except Exception as e:
    print(f"❌ Migration failed: {e}")
    print("Please check your database connection and try again.")