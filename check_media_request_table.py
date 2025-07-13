#!/usr/bin/env python3
"""
Check if media_request table exists and create it if needed
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, '/opt/stoutRequests')

def check_media_request_table():
    try:
        from app.core.database import engine
        from app.models.media_request import MediaRequest
        from sqlmodel import Session, text
        
        with Session(engine) as session:
            # Check if table exists
            try:
                result = session.exec(text("SELECT COUNT(*) FROM media_request"))
                count = result.scalar()
                print(f"✅ media_request table exists with {count} records")
                
                # Show table structure
                result = session.exec(text("""
                    SELECT column_name, data_type, is_nullable 
                    FROM information_schema.columns 
                    WHERE table_name = 'media_request' 
                    ORDER BY ordinal_position
                """))
                columns = result.all()
                print(f"📋 Table structure:")
                for col in columns:
                    print(f"   • {col[0]}: {col[1]} ({'NULL' if col[2] == 'YES' else 'NOT NULL'})")
                    
            except Exception as e:
                print(f"❌ media_request table does not exist: {e}")
                print("🔧 Creating table...")
                
                # Create all tables
                from app.core.database import create_db_and_tables
                create_db_and_tables()
                print("✅ Tables created successfully")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_media_request_table()