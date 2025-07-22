"""
Migration to add episode_number and is_episode_request fields to MediaRequest
Run this to support episode-level requests
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine

def run_migration():
    """Run the migration to add episode fields to mediarequest table"""
    print("🔄 Running migration: add_episode_fields")
    
    with engine.connect() as connection:
        # Add episode_number column
        try:
            connection.execute(text("ALTER TABLE mediarequest ADD COLUMN episode_number INTEGER"))
            print("✅ Added episode_number column")
        except Exception as e:
            if "already exists" in str(e) or "duplicate column" in str(e).lower():
                print("⚠️ episode_number column already exists")
            else:
                print(f"❌ Error adding episode_number column: {e}")
                raise
        
        # Add is_episode_request column with default value
        try:
            connection.execute(text("ALTER TABLE mediarequest ADD COLUMN is_episode_request BOOLEAN DEFAULT FALSE"))
            print("✅ Added is_episode_request column")
        except Exception as e:
            if "already exists" in str(e) or "duplicate column" in str(e).lower():
                print("⚠️ is_episode_request column already exists")
            else:
                print(f"❌ Error adding is_episode_request column: {e}")
                raise
        
        # Update existing records to have proper default values
        try:
            connection.execute(text("UPDATE mediarequest SET is_episode_request = FALSE WHERE is_episode_request IS NULL"))
            print("✅ Updated existing records with default values")
        except Exception as e:
            print(f"⚠️ Warning updating default values: {e}")
        
        # Commit the changes
        connection.commit()
    
    print("✅ Migration completed: episode fields added to mediarequest table")

if __name__ == "__main__":
    run_migration()