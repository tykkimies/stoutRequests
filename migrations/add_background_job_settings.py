#!/usr/bin/env python3
"""
Migration: Add background_job_settings column to settings table
"""

import sys
import os
sys.path.append('/opt/stoutRequests')

from sqlmodel import Session, text
from app.core.database import engine

def migrate():
    """Add background_job_settings column to settings table"""
    
    print("🔧 Adding background_job_settings column to settings table...")
    
    try:
        with Session(engine) as session:
            # Add the new column
            session.exec(text("""
                ALTER TABLE settings 
                ADD COLUMN background_job_settings VARCHAR(2000)
            """))
            
            session.commit()
            print("✅ Successfully added background_job_settings column")
            
    except Exception as e:
        if "already exists" in str(e) or "duplicate column" in str(e).lower():
            print("ℹ️ background_job_settings column already exists")
        else:
            print(f"❌ Error adding column: {e}")
            raise

if __name__ == "__main__":
    migrate()
    print("🎉 Migration completed successfully!")