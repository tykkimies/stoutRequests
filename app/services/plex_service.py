import requests
import time
from typing import List, Dict, Optional
from plexapi.server import PlexServer
from plexapi.myplex import MyPlexAccount
from sqlmodel import Session

from ..core.database import get_session
from ..services.settings_service import SettingsService
import uuid
from urllib.parse import urlencode


class PlexService:
    def __init__(self, session: Session = None, setup_mode: bool = False):
        if session is None:
            from ..core.database import engine
            self.session = Session(engine)
            self._owns_session = True
        else:
            self.session = session
            self._owns_session = False

        if setup_mode:
            print("🔧 PlexService initialized in setup mode")
            self.plex_url = None
            self.plex_token = None
            self.client_id = "plexstoutrequests"


        else:
            print("🔧 PlexService initialized in normal mode")
            config = SettingsService.get_plex_config(self.session)
            self.plex_url = config["url"]
            # Clean token immediately when loading from config to handle encoding issues
            raw_token = config["token"]
            self.plex_token = str(raw_token).encode('ascii', errors='ignore').decode('ascii').strip() if raw_token else None
            self.client_id = config.get("client_id", "stout-requests-dev")

        self.product = "plexstoutrequests"

    def __del__(self):
        if hasattr(self, "_owns_session") and self._owns_session and hasattr(self, "session"):
            self.session.close()

    def get_auth_url(self, state: Optional[str] = None) -> Dict[str, str]:
        """Generate Plex OAuth URL and PIN"""
        headers = {
            "X-Plex-Client-Identifier": self.client_id,
            "X-Plex-Product": self.product,
            "X-Plex-Version": "1.0.0",
            "X-Plex-Device": "Web Browser",
            "X-Plex-Platform": "Web",
            "Accept": "application/json"
        }

        try:
            response = requests.post("https://plex.tv/api/v2/pins", headers=headers, json={"strong": True}, timeout=10)
            response.raise_for_status()
            data = response.json()

            pin_id = data["id"]
            code = data["code"]

            auth_url = f"https://app.plex.tv/auth#?clientID={self.client_id}&code={code}"
            print(f"Generated Plex OAuth PIN: {pin_id}")
            return {
                "auth_url": auth_url,
                "pin_id": pin_id,
                "code": code,
            }
        except requests.RequestException as e:
            print(f"Error generating Plex OAuth URL: {e}")
            raise ValueError(f"Failed to connect to Plex.tv: {e}")
        except (KeyError, ValueError) as e:
            print(f"Error parsing Plex OAuth response: {e}")
            raise ValueError(f"Invalid response from Plex.tv: {e}")
    def check_pin_status(self, pin_id: int) -> Optional[str]:
        headers = {
            "X-Plex-Client-Identifier": self.client_id,
            "Accept": "application/json",
        }

        try:
            response = requests.get(f"https://plex.tv/api/v2/pins/{pin_id}", headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            print(f"✅ check_pin_status response for PIN {pin_id}: {data}")

            return data.get("authToken")
        except requests.RequestException as e:
            print(f"Error checking PIN status: {e}")
            # Don't raise exception, just return None to indicate pending
            return None
        except (KeyError, ValueError) as e:
            print(f"Error parsing PIN status response: {e}")
            return None



    def poll_for_token(self, pin_id: int, timeout: int = 300, interval: int = 5) -> Optional[str]:
        """Poll Plex to see if the PIN has been authorized and return the token"""
        headers = {
            "X-Plex-Client-Identifier": self.client_id,
            "Accept": "application/json",
        }

        end_time = time.time() + timeout

        while time.time() < end_time:
            response = requests.get(f"https://plex.tv/api/v2/pins/{pin_id}", headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get("authToken"):
                return data["authToken"]

            time.sleep(interval)

        return None

    def get_user_info(self, auth_token: str) -> Dict:
        """Get user information using auth token"""
        headers = {
            "X-Plex-Token": auth_token,
            "Accept": "application/json",
        }

        try:
            response = requests.get("https://plex.tv/api/v2/user", headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error getting user info: {e}")
            raise ValueError(f"Failed to get user info from Plex.tv: {e}")
        except (KeyError, ValueError) as e:
            print(f"Error parsing user info response: {e}")
            raise ValueError(f"Invalid user info response from Plex.tv: {e}")

    def get_user_servers(self, auth_token: str) -> List[Dict]:
        """Get user's Plex servers using auth token"""
        headers = {
            "X-Plex-Token": auth_token,
            "X-Plex-Client-Identifier": self.client_id,
            "Accept": "application/json",
        }

        try:
            response = requests.get("https://plex.tv/api/v2/resources", headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            servers = []

            for resource in data:
                if (
                    resource.get("product") == "Plex Media Server"
                    and resource.get("owned")
                    and resource.get("presence")
                    and resource.get("connections")
                ):
                    best_connection = None
                    for connection in resource.get("connections", []):
                        if connection.get("local"):
                            best_connection = connection
                            break

                    if not best_connection and resource.get("connections"):
                        best_connection = resource["connections"][0]

                    if best_connection:
                        servers.append(
                            {
                                "name": resource.get("name", "Unknown Server"),
                                "clientIdentifier": resource.get("clientIdentifier"),
                                "product": resource.get("product"),
                                "productVersion": resource.get("productVersion"),
                                "platform": resource.get("platform"),
                                "address": best_connection.get("address"),
                                "port": best_connection.get("port"),
                                "scheme": best_connection.get("protocol", "http"),
                                "local": best_connection.get("local", False),
                                "relay": best_connection.get("relay", False),
                            }
                        )

            return servers
        except requests.RequestException as e:
            print(f"Error getting user servers: {e}")
            raise ValueError(f"Failed to get servers from Plex.tv: {e}")
        except (KeyError, ValueError) as e:
            print(f"Error parsing servers response: {e}")
            raise ValueError(f"Invalid servers response from Plex.tv: {e}")

    def get_server_friends(self) -> List[Dict]:
        """Get list of Plex users using the same connection pattern as libraries"""
        try:
            # Use the same connection pattern as successful library operations
            clean_url = str(self.plex_url).encode('ascii', errors='ignore').decode('ascii').strip()
            clean_token = str(self.plex_token).encode('ascii', errors='ignore').decode('ascii').strip()
            plex = PlexServer(clean_url, clean_token)
            
            print(f"🔗 Connected to Plex server: {plex.friendlyName}")
            
            # Debug: Check what methods are available on the PlexServer object
            available_methods = [method for method in dir(plex) if not method.startswith('_') and 'user' in method.lower() or 'account' in method.lower() or 'friend' in method.lower()]
            print(f"🔍 Available user/account/friend methods on PlexServer: {available_methods}")
            
            # Debug: Check all methods that might be relevant
            all_methods = [method for method in dir(plex) if not method.startswith('_') and callable(getattr(plex, method))]
            print(f"🔍 All available methods on PlexServer: {all_methods}")
            
            friends = []
            
            # Try to get users/accounts from the PlexServer object
            try:
                # Method 1: Check if plex server has an accounts method
                if hasattr(plex, 'accounts'):
                    print("🔍 Found accounts method on PlexServer")
                    accounts = plex.accounts()
                    for account in accounts:
                        friends.append({
                            "id": getattr(account, 'id', None),
                            "username": getattr(account, 'name', getattr(account, 'username', '')),
                            "email": getattr(account, 'email', ''),
                            "title": getattr(account, 'title', getattr(account, 'name', getattr(account, 'username', ''))),
                            "thumb": getattr(account, 'thumb', ''),
                        })
                    print(f"✅ Retrieved {len(friends)} accounts from PlexServer.accounts()")
                    return friends
                    
            except Exception as e:
                print(f"❌ PlexServer.accounts() failed: {e}")
            
            # Method 2: Try users method
            try:
                if hasattr(plex, 'users'):
                    print("🔍 Found users method on PlexServer")
                    users = plex.users()
                    for user in users:
                        friends.append({
                            "id": getattr(user, 'id', None),
                            "username": getattr(user, 'name', getattr(user, 'username', '')),
                            "email": getattr(user, 'email', ''),
                            "title": getattr(user, 'title', getattr(user, 'name', getattr(user, 'username', ''))),
                            "thumb": getattr(user, 'thumb', ''),
                        })
                    print(f"✅ Retrieved {len(friends)} users from PlexServer.users()")
                    return friends
                    
            except Exception as e:
                print(f"❌ PlexServer.users() failed: {e}")
            
            # Method 3: Use PlexServer's query method to call server endpoints directly
            try:
                print("🔍 Trying direct server endpoint queries...")
                
                # Try various server endpoints that might have user/friend data
                endpoints_to_try = [
                    "/accounts",
                    "/myplex/account",
                    "/system/accounts",
                    "/users"
                ]
                
                for endpoint in endpoints_to_try:
                    try:
                        print(f"🔍 Trying endpoint: {endpoint}")
                        # Use PlexServer's query method which handles authentication properly
                        response = plex.query(endpoint)
                        
                        # PlexAPI query returns an Element object directly, not a response
                        print(f"🔍 Response type: {type(response)}")
                        print(f"🔍 Response tag: {response.tag if hasattr(response, 'tag') else 'No tag'}")
                        
                        # Look for account/user elements in the XML Element
                        print(f"🔍 Searching for users in XML response...")
                        for elem in response.iter():
                            print(f"   Found element: {elem.tag} with attributes: {elem.attrib}")
                            if elem.tag.lower() in ['account', 'user', 'friend', 'sharedserver']:
                                user_data = {
                                    "id": elem.get('id'),
                                    "username": elem.get('name', elem.get('username', elem.get('title', ''))),
                                    "email": elem.get('email', ''),
                                    "title": elem.get('title', elem.get('name', elem.get('username', ''))),
                                    "thumb": elem.get('thumb', ''),
                                }
                                print(f"   📋 Found user: {user_data}")
                                friends.append(user_data)
                        
                        if friends:
                            print(f"✅ Retrieved {len(friends)} users from {endpoint}")
                            return friends
                        else:
                            print(f"   No user elements found in {endpoint}")
                            
                            
                    except Exception as e:
                        print(f"❌ Endpoint {endpoint} failed: {e}")
                        continue
                        
            except Exception as e:
                print(f"❌ Direct endpoint queries failed: {e}")
            
            # If we get here, no users/friends were found
            print("ℹ️  No friends/users found on this Plex server. This server may not have shared users configured.")
            return []
                
        except Exception as e:
            print(f"❌ Error getting friends: {e}")
            import traceback
            traceback.print_exc()
            raise Exception(f"Failed to retrieve Plex friends: {str(e)}")

    def check_media_in_library(self, tmdb_id: int, media_type: str) -> bool:
        """Check if media exists in Plex library using TMDB ID"""
        try:
            clean_url = str(self.plex_url).encode('ascii', errors='ignore').decode('ascii').strip()
            clean_token = str(self.plex_token).encode('ascii', errors='ignore').decode('ascii').strip()
            plex = PlexServer(clean_url, clean_token)

            for library in plex.library.sections():
                if media_type == "movie" and library.type == "movie":
                    # Use library search for better performance
                    try:
                        # Try searching by TMDB ID guid
                        search_results = library.search(guid=f'tmdb://{tmdb_id}')
                        if search_results:
                            return True
                    except:
                        # Fallback to checking all movies if search fails
                        for movie in library.all():
                            for guid in movie.guids:
                                if guid.id.startswith('tmdb://') and str(tmdb_id) in guid.id:
                                    return True
                elif media_type == "tv" and library.type == "show":
                    # Use library search for better performance
                    try:
                        # Try searching by TMDB ID guid
                        search_results = library.search(guid=f'tmdb://{tmdb_id}')
                        if search_results:
                            return True
                    except:
                        # Fallback to checking all shows if search fails
                        for show in library.all():
                            for guid in show.guids:
                                if guid.id.startswith('tmdb://') and str(tmdb_id) in guid.id:
                                    return True

            return False
        except Exception as e:
            print(f"Error checking Plex library: {e}")
            return False

    def get_recently_added(self, limit: int = 20) -> List[Dict]:
        """Get recently added items from Plex library"""
        try:
            # Check if we have proper configuration
            if not self.plex_url or not self.plex_token:
                print(f"❌ Missing Plex configuration - URL: {self.plex_url}, Token: {'Yes' if self.plex_token else 'No'}")
                return []
            
            print(f"🔍 Connecting to Plex: {self.plex_url}")
            clean_url = str(self.plex_url).encode('ascii', errors='ignore').decode('ascii').strip()
            clean_token = str(self.plex_token).encode('ascii', errors='ignore').decode('ascii').strip()
            plex = PlexServer(clean_url, clean_token)
            safe_name = str(plex.friendlyName).encode('ascii', errors='ignore').decode('ascii').strip()
            print(f"🔍 Connected to Plex server: {safe_name}")
            
            # Get recently added items from all libraries
            recent_items = plex.library.recentlyAdded()  # Get all recent items
            print(f"🔍 Found {len(recent_items)} recently added items in Plex")
            
            # If we have items but they're not processing, let's try a fallback approach
            if recent_items and len(recent_items) > 0:
                print(f"🔍 Sample item details:")
                sample_item = recent_items[0]
                print(f"   Title: {getattr(sample_item, 'title', 'N/A')}")
                print(f"   Type: {getattr(sample_item, 'type', 'N/A')}")
                print(f"   GUIDs: {[g.id for g in getattr(sample_item, 'guids', [])]}")
                print(f"   Added At: {getattr(sample_item, 'addedAt', 'N/A')}")
            
            # Process items to extract relevant information
            processed_items = []
            items_without_tmdb = []
            
            for item in recent_items:
                try:
                    # Extract TMDB ID from guid if available
                    tmdb_id = None
                    guids = getattr(item, 'guids', [])
                    for guid in guids:
                        guid_id = getattr(guid, 'id', '')
                        if 'tmdb://' in guid_id:
                            tmdb_id = int(guid_id.split('tmdb://')[1])
                            break
                    
                    # Determine media type more reliably
                    item_type = getattr(item, 'type', '')
                    if item_type == 'movie':
                        media_type = 'movie'
                    elif item_type == 'show':
                        media_type = 'tv'
                    else:
                        # Fallback logic
                        media_type = 'movie' if hasattr(item, 'year') and not hasattr(item, 'seasons') else 'tv'
                    
                    # Get release date safely
                    release_date = ''
                    if hasattr(item, 'originallyAvailableAt') and item.originallyAvailableAt:
                        try:
                            release_date = item.originallyAvailableAt.strftime('%Y-%m-%d')
                        except:
                            release_date = str(item.originallyAvailableAt)[:10] if str(item.originallyAvailableAt) else ''
                    
                    if tmdb_id:
                        # Format item data similar to TMDB format
                        processed_item = {
                            'id': tmdb_id,
                            'title': item.title if media_type == 'movie' else None,
                            'name': item.title if media_type == 'tv' else None,
                            'overview': getattr(item, 'summary', ''),
                            'poster_path': None,  # Will need to be fetched from TMDB
                            'poster_url': None,
                            'release_date': release_date,
                            'first_air_date': release_date,
                            'vote_average': getattr(item, 'rating', 0) or 0,
                            'in_plex': True,  # Obviously true since it's from Plex
                            'media_type': media_type,
                            'added_at': getattr(item, 'addedAt', 0)
                        }
                        
                        processed_items.append(processed_item)
                        print(f"✅ Processed: {item.title} (TMDB: {tmdb_id}, Type: {media_type})")
                    else:
                        # Store items without TMDB ID for fallback
                        items_without_tmdb.append({
                            'title': item.title,
                            'type': media_type,
                            'guids': [g.id for g in guids] if guids else []
                        })
                        print(f"⚠️ No TMDB ID for {item.title} - GUIDs: {[g.id for g in guids] if guids else 'None'}")
                    
                except Exception as item_error:
                    print(f"⚠️ Error processing item {getattr(item, 'title', 'Unknown')}: {item_error}")
                    continue
            
            # If we have no items with TMDB IDs, let's try to use items without them
            if not processed_items and items_without_tmdb:
                print(f"🔄 No TMDB items found, trying fallback approach with {len(items_without_tmdb)} items")
                for item_info in items_without_tmdb[:limit]:
                    # Create a dummy entry for display
                    fallback_item = {
                        'id': hash(item_info['title']) % 1000000,  # Generate a fake ID for display
                        'title': item_info['title'] if item_info['type'] == 'movie' else None,
                        'name': item_info['title'] if item_info['type'] == 'tv' else None,
                        'overview': 'Recently added to your Plex server',
                        'poster_path': None,
                        'poster_url': '/static/placeholder-poster.jpg',  # Use a placeholder
                        'release_date': '',
                        'first_air_date': '',
                        'vote_average': 0,
                        'in_plex': True,
                        'media_type': item_info['type'],
                        'added_at': 0
                    }
                    processed_items.append(fallback_item)
                    print(f"🔄 Added fallback item: {item_info['title']}")
            
            # Sort by added_at timestamp (most recent first) and limit results
            processed_items.sort(key=lambda x: x.get('added_at', 0), reverse=True)
            final_items = processed_items[:limit]
            
            print(f"✅ Returning {len(final_items)} recently added items (from {len(recent_items)} total)")
            return final_items
            
        except Exception as e:
            print(f"❌ Error getting recently added from Plex: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_available_libraries(self) -> List[Dict]:
        """Get list of available Plex libraries for sync preference selection"""
        try:
            print(f"🔍 Checking Plex connection - URL: {self.plex_url}, Token: {'***' if self.plex_token else 'None'}")
            
            if not self.plex_url or not self.plex_token:
                print("❌ Plex URL or token not configured")
                
                return []
            
            print("🔗 Connecting to Plex server...")
            # Ensure URL and token are properly encoded for HTTP headers
            clean_url = str(self.plex_url).encode('ascii', errors='ignore').decode('ascii').strip()
            clean_token = str(self.plex_token).encode('ascii', errors='ignore').decode('ascii').strip()
            
            plex = PlexServer(clean_url, clean_token)
            safe_name = str(plex.friendlyName).encode('ascii', errors='ignore').decode('ascii').strip()
            print(f"✅ Connected to Plex server: {safe_name}")
            
            libraries = []
            
            print("📚 Fetching library sections...")
            for section in plex.library.sections():
                safe_title = str(section.title).encode('ascii', errors='ignore').decode('ascii').strip()
                print(f"  📖 Section: {safe_title} ({section.type})")
                if section.type in ['movie', 'show']:
                    library_info = {
                        'title': section.title,  # Keep original title for data
                        'type': section.type,
                        'key': section.key,
                        'agent': getattr(section, 'agent', 'Unknown'),
                        'language': getattr(section, 'language', 'Unknown'),
                        'refreshing': getattr(section, 'refreshing', False)
                    }
                    libraries.append(library_info)
                    print(f"    ✅ Added to list: {library_info}")
            
            print(f"📋 Total libraries found: {len(libraries)}")
            return libraries
            
        except Exception as e:
            print(f"❌ Error getting Plex libraries: {e}")
            import traceback
            traceback.print_exc()
            return []
