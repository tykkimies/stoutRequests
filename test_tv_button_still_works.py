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

async def test_tv_button_still_works():
    """Test that TV buttons still work after the movie fix"""
    
    print("📺 TEST: TV Button Still Works")
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
    print("\n📺 1. Getting TV instances:")
    tv_instances = await get_instances_for_media_type(admin_user.id, "tv")
    print(f"  TV instances: {len(tv_instances)} - {[i.name for i in tv_instances]}")
    
    # 2. Test the template macro directly
    print("\n🧰 2. Testing template macro:")
    
    # Set up Jinja2 environment
    template_dir = os.path.join(os.path.dirname(__file__), 'app', 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))
    
    # Load the macro template
    macro_template = env.get_template('macros/multi_instance_request.html')
    
    # Create a test TV item
    test_item = {
        'id': 67890,
        'name': 'Test TV Show',
        'media_type': 'tv',
        'status': 'available'
    }
    
    # Render the macro
    try:
        # Test with TV instances
        rendered = macro_template.module.multi_instance_request_button(
            item=test_item,
            user_permissions=None,
            available_instances=tv_instances,
            style='button',
            size='md',
            base_url=''
        )
        
        print(f"  Macro rendered successfully")
        print(f"  Length: {len(rendered)} characters")
        
        # Check if it contains "No Access"
        if "No Access" in rendered:
            print(f"  ❌ PROBLEM: TV macro shows 'No Access'")
            print(f"  First 200 chars: {rendered[:200]}")
        else:
            print(f"  ✓ SUCCESS: TV macro does not show 'No Access'")
            
        # Check if it contains request buttons
        if "Request" in rendered and ("sonarr" in rendered.lower() or "bg-orange" in rendered):
            print(f"  ✓ SUCCESS: TV macro contains request buttons")
        else:
            print(f"  ❌ PROBLEM: TV macro doesn't contain request buttons")
            
    except Exception as e:
        print(f"  ❌ ERROR rendering TV macro: {e}")
        import traceback
        traceback.print_exc()
    
    session.close()
    
    print("\n" + "=" * 50)
    print("📺 TV button test complete!")

if __name__ == "__main__":
    asyncio.run(test_tv_button_still_works())
