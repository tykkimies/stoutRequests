#!/usr/bin/env python3

import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

def test_plex_oauth():
    client_id = 'stout-requests'
    headers = {
        'X-Plex-Client-Identifier': client_id,
        'X-Plex-Product': 'Stout Requests',
        'X-Plex-Version': '1.0.0',
        'X-Plex-Platform': 'Web',
        'X-Plex-Platform-Version': '1.0.0',
        'X-Plex-Device': 'Web Browser',
        'X-Plex-Device-Name': 'Stout Requests',
        'Accept': 'application/xml'
    }
    
    print("1. Creating PIN...")
    response = requests.post('https://plex.tv/api/v2/pins', headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 201:
        root = ET.fromstring(response.text)
        pin_id = root.get('id')
        code = root.get('code')
        
        print(f"2. PIN ID: {pin_id}")
        print(f"   Code: {code}")
        
        # Generate auth URL with correct format
        params = {
            'clientID': client_id,
            'code': code,
            'context[device][product]': 'Stout Requests'
        }
        auth_url = f"https://app.plex.tv/auth#?{urlencode(params)}"
        
        print(f"3. Auth URL: {auth_url}")
        print("4. Test this URL in your browser!")
        
        return pin_id, auth_url
    else:
        print("Failed to create PIN")
        return None, None

if __name__ == "__main__":
    test_plex_oauth()