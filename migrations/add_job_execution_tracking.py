#!/usr/bin/env python3
"""
Migration: Add job_executions table for tracking job history
"""

import sys
import os
sys.path.append('/opt/stoutRequests')

from sqlmodel import Session, text
from app.core.database import engine

def migrate():
    """Add job_executions table for tracking job execution history"""
    
    print("🔧 Creating job_executions table...")
    
    try:
        with Session(engine) as session:
            # Create the job_executions table
            session.exec(text("""
                CREATE TABLE IF NOT EXISTS job_executions (
                    id SERIAL PRIMARY KEY,
                    job_name VARCHAR(100) NOT NULL,
                    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'running',
                    result_data JSON NULL,
                    error_message TEXT NULL,
                    triggered_by VARCHAR(50) NOT NULL DEFAULT 'scheduler',
                    duration_seconds FLOAT NULL
                )
            """))
            
            # Add index on job_name for faster queries
            session.exec(text("""
                CREATE INDEX IF NOT EXISTS idx_job_executions_job_name 
                ON job_executions(job_name)
            """))
            
            # Add index on started_at for chronological queries
            session.exec(text("""
                CREATE INDEX IF NOT EXISTS idx_job_executions_started_at 
                ON job_executions(started_at DESC)
            """))
            
            session.commit()
            print("✅ Successfully created job_executions table with indexes")
            
    except Exception as e:
        if "already exists" in str(e).lower():
            print("ℹ️ job_executions table already exists")
        else:
            print(f"❌ Error creating table: {e}")
            raise

if __name__ == "__main__":
    migrate()
    print("🎉 Migration completed successfully!")