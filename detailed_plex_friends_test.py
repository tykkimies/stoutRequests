#!/usr/bin/env python3
"""
Detailed test of Plex friends/users functionality
"""
import sys
import os
import requests

# Add the app directory to the path
sys.path.insert(0, '/opt/stoutRequests')

def test_plex_friends_detailed():
    try:
        from app.core.database import engine
        from app.services.plex_service import PlexService
        from app.services.settings_service import SettingsService
        from sqlmodel import Session
        
        with Session(engine) as session:
            # Get Plex config
            config = SettingsService.get_plex_config(session)
            plex_token = config.get('token')
            
            if not plex_token:
                print("❌ No Plex token found")
                return
                
            print(f"🔍 Testing with Plex token: ***{plex_token[-4:]}")
            
            # Test direct API calls
            headers = {
                "X-Plex-Token": plex_token,
                "Accept": "application/json",
            }
            
            print("\n1. Testing /api/v2/user endpoint:")
            try:
                response = requests.get("https://plex.tv/api/v2/user", headers=headers, timeout=10)
                if response.status_code == 200:
                    user_data = response.json()
                    print(f"   ✅ User: {user_data.get('username')} (ID: {user_data.get('id')})")
                    print(f"   Email: {user_data.get('email')}")
                    print(f"   Home: {user_data.get('home', False)}")
                    print(f"   Home Admin: {user_data.get('homeAdmin', False)}")
                else:
                    print(f"   ❌ Failed: {response.status_code}")
            except Exception as e:
                print(f"   ❌ Error: {e}")
            
            print("\n2. Testing /api/v2/friends endpoint:")
            try:
                response = requests.get("https://plex.tv/api/v2/friends", headers=headers, timeout=10)
                print(f"   Status: {response.status_code}")
                if response.status_code == 200:
                    friends_data = response.json()
                    print(f"   Friends found: {len(friends_data) if isinstance(friends_data, list) else 'Not a list'}")
                    if isinstance(friends_data, list) and friends_data:
                        for friend in friends_data[:3]:  # Show first 3
                            print(f"     • {friend.get('username', 'N/A')} ({friend.get('email', 'N/A')})")
                    else:
                        print(f"   Raw response: {friends_data}")
                else:
                    print(f"   Error response: {response.text}")
            except Exception as e:
                print(f"   ❌ Error: {e}")
            
            print("\n3. Testing /api/home/users endpoint:")
            try:
                response = requests.get("https://plex.tv/api/home/users", headers=headers, timeout=10)
                print(f"   Status: {response.status_code}")
                if response.status_code == 200:
                    home_users = response.json()
                    print(f"   Home users found: {len(home_users) if isinstance(home_users, list) else 'Not a list'}")
                    if isinstance(home_users, list) and home_users:
                        for user in home_users[:3]:  # Show first 3
                            print(f"     • {user.get('username', user.get('title', 'N/A'))} (ID: {user.get('id')})")
                            print(f"       Admin: {user.get('admin', False)}, Protected: {user.get('protected', False)}")
                    else:
                        print(f"   Raw response: {home_users}")
                else:
                    print(f"   Error response: {response.text}")
            except Exception as e:
                print(f"   ❌ Error: {e}")
            
            print("\n4. Testing PlexService get_server_friends():")
            plex_service = PlexService(session)
            friends = plex_service.get_server_friends()
            print(f"   Friends from service: {len(friends)}")
            for friend in friends:
                print(f"     • {friend}")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_plex_friends_detailed()