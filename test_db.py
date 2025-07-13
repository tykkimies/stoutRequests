#!/usr/bin/env python3
"""
Test database connection and basic functionality
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_database_connection():
    """Test database connection"""
    try:
        from app.core.database import engine
        from sqlmodel import text
        
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            print("✅ Database connection successful")
            return True
            
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\n💡 Make sure:")
        print("1. PostgreSQL is running")
        print("2. Database exists: CREATE DATABASE stout_requests;")
        print("3. DATABASE_URL in .env is correct")
        return False

def test_create_tables():
    """Test table creation"""
    try:
        from app.core.database import create_db_and_tables
        
        create_db_and_tables()
        print("✅ Database tables created successfully")
        return True
        
    except Exception as e:
        print(f"❌ Table creation failed: {e}")
        return False

def test_env_config():
    """Test environment configuration"""
    try:
        from app.core.config import settings
        
        required_settings = [
            'database_url',
            'secret_key'
        ]
        
        missing = []
        for setting in required_settings:
            if not getattr(settings, setting):
                missing.append(setting)
        
        if missing:
            print(f"❌ Missing required settings: {', '.join(missing)}")
            return False
        else:
            print("✅ Required environment settings found")
            return True
            
    except Exception as e:
        print(f"❌ Environment config test failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Database Setup\n")
    
    print("1. Testing environment configuration...")
    env_ok = test_env_config()
    
    if env_ok:
        print("\n2. Testing database connection...")
        db_ok = test_database_connection()
        
        if db_ok:
            print("\n3. Testing table creation...")
            tables_ok = test_create_tables()
            
            if tables_ok:
                print("\n🎉 Database setup complete!")
                print("\n📝 You can now run: python run.py")
            else:
                print("\n⚠️  Table creation failed")
        else:
            print("\n⚠️  Database connection failed")
    else:
        print("\n⚠️  Environment configuration incomplete")
        print("Make sure to copy .env.example to .env and configure it")