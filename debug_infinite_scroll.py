#!/usr/bin/env python3
"""
Debug script to test infinite scroll permissions
"""
import sys
sys.path.append('/opt/stoutRequests')

from sqlmodel import Session, select
from app.core.database import get_session
from app.models import User
from app.services.instance_selection_service import InstanceSelectionService
from app.main import create_template_response_with_instances
from fastapi import Request
import asyncio

class MockRequest:
    def __init__(self):
        self.headers = {"HX-Request": "true", "HX-Target": "results-grid"}
        self.url = "http://localhost/discover/category/more?type=movie&sort=trending&page=2"

async def debug_infinite_scroll():
    """Debug infinite scroll permissions"""
    print("🔍 Debug Infinite Scroll Permissions")
    print("=" * 50)
    
    # Get database session
    session = next(get_session())
    
    # Get server admin user
    server_admin = session.exec(select(User).where(User.is_server_owner == True)).first()
    if not server_admin:
        print("❌ No server admin found")
        return
    
    print(f"👑 Testing infinite scroll for: {server_admin.username} (ID: {server_admin.id})")
    print(f"   - is_admin: {server_admin.is_admin}")
    print(f"   - is_server_owner: {server_admin.is_server_owner}")
    
    # Test getting available instances directly
    instance_service = InstanceSelectionService(session)
    print(f"\n🎯 Direct instance check:")
    print(f"   - User ID passed to service: {server_admin.id}")
    print(f"   - User type check - is_admin: {server_admin.is_admin}")
    print(f"   - User type check - is_server_owner: {server_admin.is_server_owner}")
    
    # Test the movie_cards_only template context
    print(f"\n🎬 Testing movie_cards_only template context:")
    mock_request = MockRequest()
    
    test_context = {
        'request': mock_request,
        'current_user': server_admin,
        'results': [
            {
                'id': 123,
                'title': 'Test Movie',
                'media_type': 'movie',
                'poster_url': 'test.jpg',
                'vote_average': 8.5,
                'release_date': '2023-01-01'
            }
        ],
        'media_type': 'movie',
        'current_page': 2,
        'has_more': True
    }
    
    try:
        print(f"   🔧 Calling create_template_response_with_instances...")
        print(f"   🔧 Template: components/movie_cards_only.html")
        print(f"   🔧 User in context: {test_context['current_user'].username}")
        
        # This should populate available_instances
        response = await create_template_response_with_instances(
            "components/movie_cards_only.html",
            test_context
        )
        print(f"   ✅ Template response created successfully")
        print(f"   ✅ Response type: {type(response)}")
        
    except Exception as e:
        print(f"   ❌ Error creating template response: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n🎉 Debug Complete!")

if __name__ == "__main__":
    asyncio.run(debug_infinite_scroll())