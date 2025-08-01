#!/usr/bin/env python3

import asyncio
import sys
sys.path.append('/opt/stoutRequests')

from app.core.database import get_session
from app.models.user import User
from sqlmodel import Session, select
from app.main import get_instances_for_media_type
from jinja2 import Environment, FileSystemLoader
import os

async def test_movie_button_fix():
    """Test that the movie button fix works correctly"""
    
    print("🧪 TEST: Movie Button Fix")
    print("=" * 50)
    
    # Get database session
    session = next(get_session()) 
    
    # Get admin user
    users_stmt = select(User).where(User.is_admin == True)
    admin_users = session.exec(users_stmt).all()
    admin_user = admin_users[0] if admin_users else None
    
    if not admin_user:
        print("❌ No admin user found")
        return
    
    print(f"👤 Using admin user: {admin_user.username}")
    
    # 1. Get instances like the endpoint would
    print("\n🎥 1. Getting movie instances:")
    movie_instances = await get_instances_for_media_type(admin_user.id, "movie")
    print(f"  Movie instances: {len(movie_instances)} - {[i.name for i in movie_instances]}")
    
    # 2. Test the template macro directly
    print("\n🧰 2. Testing template macro:")
    
    # Set up Jinja2 environment
    template_dir = os.path.join(os.path.dirname(__file__), 'app', 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))
    
    # Load the macro template
    macro_template = env.get_template('macros/multi_instance_request.html')
    
    # Create a test context
    test_item = {
        'id': 12345,
        'title': 'Test Movie',
        'media_type': 'movie',
        'status': 'available'
    }
    
    # Render the macro
    try:
        macro_context = {
            'multi_instance_request_button': macro_template.module.multi_instance_request_button
        }
        
        # Test with movie instances
        rendered = macro_template.module.multi_instance_request_button(
            item=test_item,
            user_permissions=None,
            available_instances=movie_instances,
            style='button',
            size='md',
            base_url=''
        )
        
        print(f"  Macro rendered successfully")
        print(f"  Length: {len(rendered)} characters")
        
        # Check if it contains "No Access"
        if "No Access" in rendered:
            print(f"  ❌ PROBLEM: Macro still shows 'No Access'")
            print(f"  First 200 chars: {rendered[:200]}")
        else:
            print(f"  ✓ SUCCESS: Macro does not show 'No Access'")
            
        # Check if it contains request buttons
        if "Request" in rendered and ("radarr" in rendered.lower() or "bg-orange" in rendered):
            print(f"  ✓ SUCCESS: Macro contains request buttons")
        else:
            print(f"  ❌ PROBLEM: Macro doesn't contain request buttons")
            
    except Exception as e:
        print(f"  ❌ ERROR rendering macro: {e}")
        import traceback
        traceback.print_exc()
    
    session.close()
    
    print("\n" + "=" * 50)
    print("🧪 Movie button fix test complete!")

if __name__ == "__main__":
    asyncio.run(test_movie_button_fix())
