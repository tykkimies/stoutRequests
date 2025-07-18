from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from sqlmodel import Session, select
from typing import Optional
import uuid
from datetime import timedelta

from ..core.database import get_session
from ..core.auth import create_access_token, verify_token
from ..core.config import settings
from ..models.user import User
from ..services.plex_service import PlexService

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()

# Store for PIN verification (in production, use Redis)
pin_store = {}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(get_session)
) -> User:
    """Get current authenticated user"""
    username = verify_token(credentials.credentials)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    statement = select(User).where(User.username == username, User.is_active == True)
    user = session.exec(statement).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user


async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current user if they are an admin"""
    # Import here to avoid circular imports
    from ..core.database import get_session
    from ..core.permissions import is_user_admin
    
    # Check admin permissions using new unified function
    with next(get_session()) as session:
        if not is_user_admin(current_user, session):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
    
    return current_user


async def get_current_admin_user_flexible(
    request: Request,
    session: Session = Depends(get_session)
) -> User:
    """Get current admin user using flexible authentication (headers + cookies)"""
    try:
        # Use the same flexible authentication as get_current_user_optional
        auth_header = request.headers.get("authorization")
        token = None
        
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
        else:
            # Check for token in cookies as fallback
            token = request.cookies.get("access_token")
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )
        
        # Verify token and get user
        from ..core.auth import verify_token
        username = verify_token(token)
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        statement = select(User).where(User.username == username)
        user = session.exec(statement).first()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check admin permissions using new unified function
        from ..core.permissions import is_user_admin
        if not is_user_admin(user, session):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Admin auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )


async def get_current_user_flexible(
    request: Request,
    session: Session = Depends(get_session)
) -> User:
    """Get current user using flexible authentication (headers + cookies)"""
    try:
        # Use the same flexible authentication as get_current_user_optional
        auth_header = request.headers.get("authorization")
        token = None
        
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
        else:
            # Check for token in cookies as fallback
            token = request.cookies.get("access_token")
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )
        
        # Verify token and get user
        from ..core.auth import verify_token
        username = verify_token(token)
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        statement = select(User).where(User.username == username)
        user = session.exec(statement).first()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"User auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )


@router.get("/plex/login")
async def plex_login(request: Request, session: Session = Depends(get_session)):
    """Initiate Plex OAuth flow"""
    try:
        # Get base URL for proper URL construction
        from ..services.settings_service import SettingsService
        base_url = SettingsService.get_base_url(session)
        
        plex_service = PlexService(session)
        state = str(uuid.uuid4())
        auth_data = plex_service.get_auth_url(state)
        
        # Store PIN data for verification
        pin_store[auth_data['pin_id']] = {
            'code': auth_data['code'],
            'state': state
        }
        
        # Return HTML response for HTMX
        from fastapi.responses import HTMLResponse
        html_content = f"""
        <div id="login-oauth-content">
            <div class="text-center">
                <div class="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                    <svg class="w-8 h-8 text-blue-600 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                    </svg>
                </div>
                <h3 class="text-lg font-semibold text-gray-900 mb-2">Opening Plex Authorization...</h3>
                <p class="text-gray-600 mb-4">A popup/tab should open automatically</p>
                <div class="space-y-3">
                    <button type="button" onclick="openPlexAuthLogin('{auth_data['auth_url']}')" 
                            class="bg-gray-600 hover:bg-gray-700 text-white px-6 py-2 rounded-md text-sm font-medium w-full">
                        🔗 Didn't open? Click here
                    </button>
                    <p class="text-xs text-gray-500">Manual link: <a href="{auth_data['auth_url']}" target="_blank" class="text-orange-600 underline">Open Plex Authorization</a></p>
                    <p class="text-xs text-gray-500 mt-3">✅ Waiting for authorization... (checking every second)</p>
                </div>
            </div>
        </div>
        
        <script>
            function openPlexAuthLogin(url) {{
                const popup = window.open(url, 'plex-auth', 'width=600,height=700,scrollbars=yes,resizable=yes');
                if (!popup || popup.closed || typeof popup.closed == 'undefined') {{
                    window.open(url, '_blank');
                }}
            }}
            
            // Auto-open popup
            setTimeout(() => {{
                openPlexAuthLogin('{auth_data['auth_url']}');
            }}, 100);
            
            // Start polling for authorization immediately with faster intervals
            let attempts = 0;
            const maxAttempts = 180; // 3 minutes total (180 * 1 second)
            
            // Start polling immediately after popup opens
            setTimeout(() => {{
                const pollInterval = setInterval(async () => {{
                    attempts++;
                    if (attempts > maxAttempts) {{
                        clearInterval(pollInterval);
                        document.getElementById('login-oauth-content').innerHTML = `
                            <div class="text-center text-red-600">
                                <p>⏰ Authorization timed out. Please try again.</p>
                                <button onclick="location.reload()" class="mt-2 bg-orange-600 text-white px-4 py-2 rounded">
                                    Try Again
                                </button>
                            </div>
                        `;
                        return;
                    }}
                    
                    try {{
                        const response = await fetch('{base_url}/auth/plex/verify', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
                            body: 'pin_id={auth_data['pin_id']}',
                            redirect: 'follow'
                        }});
                        
                        if (response.status === 200) {{
                            const data = await response.json();
                            if (data.access_token) {{
                                // Success! Store token in localStorage and set header for future requests
                                localStorage.setItem('access_token', data.access_token);
                                
                                // Create a cookie for server-side rendering (optional)
                                document.cookie = `access_token=${{data.access_token}}; path=/; max-age=86400`;
                                
                                clearInterval(pollInterval);
                                
                                // Show success message briefly
                                document.getElementById('login-oauth-content').innerHTML = `
                                    <div class="text-center text-green-600">
                                        <div class="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
                                            <svg class="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                                            </svg>
                                        </div>
                                        <h3 class="text-lg font-semibold text-gray-900 mb-2">✅ Authorization Successful!</h3>
                                        <p class="text-gray-600">Redirecting to dashboard...</p>
                                    </div>
                                `;
                                
                                // Redirect after brief success message
                                setTimeout(() => {{
                                    window.location.href = '{base_url}/?logged_in=true';
                                }}, 1000);
                            }} else if (data.status === 'pending') {{
                                // Still waiting for authorization - update status
                                const waitTime = Math.floor(attempts * 1);
                                document.querySelector('.text-xs.text-gray-500.mt-3').textContent = 
                                    `⏳ Waiting for authorization... (${{waitTime}}s elapsed)`;
                            }}
                        }} else if (response.status === 403) {{
                            // Handle unauthorized access
                            const data = await response.json();
                            if (data.status === 'unauthorized' && data.redirect_url) {{
                                clearInterval(pollInterval);
                                
                                // Show brief message then redirect
                                document.getElementById('login-oauth-content').innerHTML = `
                                    <div class="text-center text-yellow-600">
                                        <div class="w-16 h-16 bg-yellow-100 rounded-full flex items-center justify-center mx-auto mb-4">
                                            <svg class="w-8 h-8 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.464 0L4.35 16.5c-.77.833.192 2.5 1.732 2.5z"></path>
                                            </svg>
                                        </div>
                                        <h3 class="text-lg font-semibold text-gray-900 mb-2">✅ Authentication Successful!</h3>
                                        <p class="text-gray-600">Redirecting to access request page...</p>
                                    </div>
                                `;
                                
                                // Redirect to unauthorized page
                                setTimeout(() => {{
                                    window.location.href = data.redirect_url;
                                }}, 1500);
                            }}
                        }}
                    }} catch (err) {{
                        console.log('Polling error:', err);
                    }}
                }}, 1000); // Poll every 1 second instead of 5
            }}, 2000); // Start polling after 2 seconds instead of 7
        </script>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=f"""
        <div class="text-center text-red-600">
            <p>Error initiating Plex login: {str(e)}</p>
            <button onclick="location.reload()" class="mt-2 bg-orange-600 text-white px-4 py-2 rounded">
                Try Again
            </button>
        </div>
        """)


@router.post("/plex/verify")
async def plex_verify(request: Request, pin_id: str = Form(...), session: Session = Depends(get_session)):
    """Verify Plex PIN and create/login user"""
    try:
        # Get base URL for proper URL construction
        from ..services.settings_service import SettingsService
        base_url = SettingsService.get_base_url(session)
        
        pin_id_int = int(pin_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid PIN format")
    
    if pin_id_int not in pin_store:
        raise HTTPException(status_code=400, detail="Invalid PIN ID")
    
    plex_service = PlexService(session)
    
    # Check PIN status
    auth_token = plex_service.check_pin_status(pin_id_int)
    if not auth_token:
        return JSONResponse(content={"status": "pending", "pin_id": pin_id_int}, status_code=200)
    
    # Get user info from Plex
    user_info = plex_service.get_user_info(auth_token)
    
    # Check if user exists by plex_id first
    print(f"🔍 Looking for user with plex_id: {user_info['id']}")
    statement = select(User).where(User.plex_id == user_info['id'])
    existing_user = session.exec(statement).first()
    
    # If not found by plex_id, try by username (in case plex_id changed)
    if not existing_user:
        print(f"🔍 Plex_id not found, trying username: {user_info['username']}")
        username_statement = select(User).where(User.username == user_info['username'])
        existing_user = session.exec(username_statement).first()
        
        if existing_user:
            print(f"✅ Found user by username, updating plex_id: {existing_user.username}")
            # Update the plex_id to the current one from Plex
            existing_user.plex_id = user_info['id']
            session.add(existing_user)
            session.commit()
    
    if existing_user:
        print(f"✅ Found existing user: {existing_user.username} (admin: {existing_user.is_admin})")
        if not existing_user.is_active:
            raise HTTPException(status_code=403, detail="Account is disabled")
        user = existing_user
    else:
        print(f"❌ No user found with plex_id: {user_info['id']} or username: {user_info['username']}")
        print(f"🔍 User info from Plex: {user_info}")
        
        # Check if this is the very first user (admin setup)
        admin_statement = select(User).where(User.is_admin == True)
        admin_exists = session.exec(admin_statement).first()
        print(f"🔍 Admin exists: {admin_exists is not None}")
        
        if admin_exists:
            print(f"🔍 Existing admin: {admin_exists.username} (plex_id: {admin_exists.plex_id})")
        
        if not admin_exists:
            # First user becomes admin automatically
            user = User(
                plex_id=user_info['id'],
                username=user_info['username'],
                email=user_info.get('email'),
                full_name=user_info.get('title', user_info['username']),
                avatar_url=user_info.get('thumb'),
                is_admin=True
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            
            # If this is the first user and settings are configured, set them as the configurator
            from ..services.settings_service import SettingsService
            SettingsService.set_configured_by_first_user(session)
        else:
            # User doesn't exist and admin already exists - log the attempt and redirect to unauthorized page
            print(f"🚫 Unauthorized access attempt by Plex user: {user_info['username']} (ID: {user_info['id']})")
            
            # TODO: In a production system, you might want to:
            # 1. Log this to a proper logging system
            # 2. Send notification to administrators
            # 3. Store the access request in a database table for admin review
            
            # Create a special response that the frontend can handle
            from ..services.settings_service import build_app_url
            return JSONResponse(
                content={
                    "status": "unauthorized",
                    "message": "Access request pending",
                    "username": user_info['username'],
                    "redirect_url": build_app_url(f"/unauthorized?username={user_info['username']}")
                },
                status_code=403
            )
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id},
        expires_delta=access_token_expires
    )
    
    # Clean up PIN store
    del pin_store[pin_id_int]
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "is_admin": user.is_admin
        }
    }


@router.post("/import-friends")
async def import_plex_friends(
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    session: Session = Depends(get_session)
):
    """Import Plex friends (admin only) - supports both HTMX and API clients"""
    plex_service = PlexService(session)
    friends = plex_service.get_server_friends()
    
    imported_count = 0
    for friend_data in friends:
        # Check if user already exists
        statement = select(User).where(User.plex_id == friend_data['id'])
        existing_user = session.exec(statement).first()
        
        if not existing_user:
            user = User(
                plex_id=friend_data['id'],
                username=friend_data['username'],
                email=friend_data.get('email'),
                full_name=friend_data.get('title', friend_data['username']),
                avatar_url=friend_data.get('thumb'),
                is_local_user=False,  # Plex friends are not local users
                is_active=True
            )
            session.add(user)
            imported_count += 1
    
    session.commit()
    
    # Content negotiation: HTMX vs API clients
    if request.headers.get("HX-Request"):
        # HTMX request - return HTML that shows success and refreshes users list
        from fastapi.responses import HTMLResponse
        return HTMLResponse(f"""
            <div class="p-4 bg-green-50 border border-green-200 rounded-md mb-4">
                <div class="flex">
                    <svg class="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                    </svg>
                    <p class="ml-3 text-sm text-green-700">Imported {imported_count} new users successfully!</p>
                </div>
            </div>
        """)
    else:
        # API request (mobile app, etc.) - return JSON
        return {"success": True, "message": f"Imported {imported_count} new users"}


# Local Authentication Endpoints

@router.get("/local/login")
async def local_login_form(request: Request, session: Session = Depends(get_session)):
    """Display local login form"""
    # Get base URL for proper URL construction
    from ..services.settings_service import SettingsService
    base_url = SettingsService.get_base_url(session)
    
    from fastapi.responses import HTMLResponse
    html_content = f"""
    <div class="space-y-6">
        <div class="text-center">
            <h3 class="text-lg font-semibold text-gray-900 mb-2">Local Account Login</h3>
            <p class="text-gray-600 mb-4">Sign in with your local account credentials</p>
        </div>
        
        <div id="local-login-error" class="hidden p-3 bg-red-50 border border-red-200 rounded-md">
            <p class="text-red-700 text-sm"></p>
        </div>
        
        <form id="local-login-form" class="space-y-4">
            <div>
                <label for="local-username" class="block text-sm font-medium text-gray-700">Username</label>
                <input type="text" name="username" id="local-username" 
                       class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-orange-500 focus:border-orange-500"
                       placeholder="Enter your username" required>
            </div>
            
            <div>
                <label for="local-password" class="block text-sm font-medium text-gray-700">Password</label>
                <input type="password" name="password" id="local-password" 
                       class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-orange-500 focus:border-orange-500"
                       placeholder="Enter your password" required>
            </div>
            
            <div class="flex items-center justify-between">
                <button type="button" onclick="showPlexLogin()" 
                        class="text-sm text-orange-600 hover:text-orange-500">
                    ← Back to Plex Login
                </button>
                
                <button type="submit" 
                        class="bg-orange-600 hover:bg-orange-700 text-white px-6 py-2 rounded-md text-sm font-medium">
                    Sign In
                </button>
            </div>
        </form>
    </div>
    
    <script>
        document.getElementById('local-login-form').addEventListener('submit', async (e) => {{
            e.preventDefault();
            
            const formData = new FormData(e.target);
            const username = formData.get('username');
            const password = formData.get('password');
            
            try {{
                const response = await fetch('{base_url}/auth/local/verify', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{
                        username: username,
                        password: password
                    }})
                }});
                
                const result = await response.json();
                
                if (response.ok) {{
                    // Set token and redirect
                    if (result.access_token) {{
                        localStorage.setItem('access_token', result.access_token);
                        document.cookie = `access_token=${{result.access_token}}; path=/; max-age=86400`;
                        window.location.href = '{base_url}/';
                    }}
                }} else {{
                    // Show error
                    const errorDiv = document.getElementById('local-login-error');
                    errorDiv.querySelector('p').textContent = result.detail || 'Login failed';
                    errorDiv.classList.remove('hidden');
                }}
            }} catch (error) {{
                console.error('Login error:', error);
                const errorDiv = document.getElementById('local-login-error');
                errorDiv.querySelector('p').textContent = 'Network error. Please try again.';
                errorDiv.classList.remove('hidden');
            }}
        }});
        
        function showPlexLogin() {{
            htmx.ajax('GET', '{base_url}/auth/plex/login', '#login-content');
        }}
    </script>
    """
    return HTMLResponse(content=html_content)


@router.post("/local/verify")
async def local_login_verify(
    request: Request,
    session: Session = Depends(get_session)
):
    """Verify local login credentials"""
    from ..core.password import verify_password
    
    try:
        # Get JSON data from request
        data = await request.json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            raise HTTPException(
                status_code=400,
                detail="Username and password are required"
            )
        
        # Find local user
        statement = select(User).where(
            User.username == username,
            User.is_local_user == True,
            User.is_active == True
        )
        user = session.exec(statement).first()
        
        if not user or not user.has_password():
            raise HTTPException(
                status_code=401,
                detail="Invalid username or password"
            )
        
        # Verify password
        if not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=401,
                detail="Invalid username or password"
            )
        
        # Create access token
        access_token = create_access_token(data={"sub": user.username})
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "is_admin": user.is_admin,
                "is_local_user": user.is_local_user
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )