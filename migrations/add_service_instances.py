"""
Migration to add service_instance table for multiple Radarr/Sonarr instances
Run this after creating the ServiceInstance model
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import create_engine, SQLModel
from app.models.service_instance import ServiceInstance
from app.core.database import engine

def run_migration():
    """Run the migration to create service_instance table"""
    print("🔄 Running migration: add_service_instances")
    
    # Create the new table
    SQLModel.metadata.create_all(engine, tables=[ServiceInstance.__table__])
    
    print("✅ Migration completed: service_instance table created")

if __name__ == "__main__":
    run_migration()