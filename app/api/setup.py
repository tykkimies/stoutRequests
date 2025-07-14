from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from typing import Optional

from ..core.database import get_session
from ..models.user import User
from ..models.settings import Settings
from ..services.settings_service import SettingsService, build_app_url
from fastapi.responses import JSONResponse
from ..services.plex_service import PlexService
from ..api.auth import pin_store
from ..services.plex_service import PlexService

router = APIRouter(prefix="/setup", tags=["setup"])
templates = Jinja2Templates(directory="app/templates")
# print("🔧 setup.py loaded!") 
# @router.get("/test-plex-auth")
# async def test_plex_auth():
#     try:
#         plex = PlexService(setup_mode=True)
#         return JSONResponse(plex.get_auth_url())
#     except Exception as e:
#         return JSONResponse({"error": str(e)}, status_code=500)
    
@router.get("/", response_class=HTMLResponse)
async def setup_wizard(
    request: Request,
    session: Session = Depends(get_session)
):
    """First-time setup wizard"""
    # Check if already configured
    if SettingsService.is_configured(session):
        return RedirectResponse(url=build_app_url("/"), status_code=303)
    
    # Check if any users exist
    statement = select(User)
    users = session.exec(statement).all()
    has_users = len(users) > 0
    
    # Get base_url for template
    base_url = SettingsService.get_base_url(session)
    
    # Use global template context for consistent base_url handling
    from ..core.template_context import get_global_template_context
    global_context = get_global_template_context()
    
    context = {
        "request": request,
        "has_users": has_users,
        "step": request.query_params.get("step", "1"),
        **global_context  # Include global context (base_url, etc.)
    }
    
    return templates.TemplateResponse("setup_wizard.html", context)



@router.get("/plex-oauth")
async def setup_plex_oauth(session: Session = Depends(get_session)):
    """Initiate Plex OAuth for setup"""
    try:
        from ..services.plex_service import PlexService
        
        # Create a temporary plex service for OAuth (no session config needed)
        plex_service = PlexService(session, setup_mode=True)
        
        import uuid
        state = str(uuid.uuid4())
        auth_data = plex_service.get_auth_url(state)
        
        # Store PIN data for verification (in production, use Redis)
        from ..api.auth import pin_store
        pin_store[auth_data['pin_id']] = {
            'code': auth_data['code'],
            'state': state,
            'setup_mode': True  # Flag to indicate this is for setup
        }
        
        return {
            "auth_url": auth_data['auth_url'],
            "pin_id": auth_data['pin_id']
        }
    except ValueError as e:
        # Handle Plex service errors
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Unexpected error in setup_plex_oauth: {e}")
        raise HTTPException(status_code=500, detail="Failed to initiate Plex OAuth")


@router.post("/plex-verify")
async def setup_plex_verify(
    pin_id: str = Form(...),
    session: Session = Depends(get_session),
):
    """
    Verify Plex OAuth PIN status.
    If authorized, redirect to success page (303).
    If still pending, return 200 OK (polling continues).
    If error or invalid PIN, redirect to error page (303).
    """
    try:
        pin_id_int = int(pin_id)  # Convert to integer for API calls
    except ValueError:
        return RedirectResponse(
            url="/setup?step=1&error=Invalid PIN format",
            status_code=303
        )
    
    print(f"Verifying Plex PIN: {pin_id_int} (type: {type(pin_id_int)}), in {pin_store}")
    if pin_id_int not in pin_store:
        print(f"Invalid PIN ID: {pin_id_int}")
        # Invalid PIN - redirect with error
        return RedirectResponse(
            url="/setup?step=1&error=Invalid PIN ID",
            status_code=303
        )

    try:
        plex_service = PlexService(session, setup_mode=True)
        print(f"About to check PIN status for {pin_id_int}")
        auth_token = plex_service.check_pin_status(pin_id_int)

        if not auth_token:
            print(f"PIN {pin_id_int} not authorized yet, polling...")
            # PIN not authorized yet, return 200 OK for JS to keep polling
            return JSONResponse(
                content={"status": "pending", "pin_id": pin_id_int}, 
                status_code=200,
                headers={"Content-Type": "application/json"}
            )

        # PIN authorized! Get user info & servers
        user_info = plex_service.get_user_info(auth_token)
        servers = plex_service.get_user_servers(auth_token)

        if not servers:
            print("No servers found for this account")
            return RedirectResponse(
                url="/setup?step=1&error=No Plex servers found for this account",
                status_code=303
            )

        # Create user account from Plex info (or get existing user)
        from ..models.user import User
        from sqlmodel import select
        
        statement = select(User).where(User.plex_id == user_info['id'])
        existing_user = session.exec(statement).first()
        
        if existing_user:
            if not existing_user.is_active:
                return RedirectResponse(
                    url="/setup?step=1&error=Your account is disabled",
                    status_code=303
                )
            user = existing_user
        else:
            # Create new user - first user becomes admin
            from sqlmodel import select
            user_count = len(session.exec(select(User)).all())
            is_first_user = user_count == 0
            
            user = User(
                plex_id=user_info['id'],
                username=user_info['username'],
                email=user_info.get('email'),
                full_name=user_info.get('title', user_info['username']),
                avatar_url=user_info.get('thumb'),
                is_admin=is_first_user,  # First user is admin
                is_server_owner=is_first_user  # First user is server owner
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        
        # Generate access token for automatic login
        from ..core.auth import create_access_token
        from ..core.config import settings
        from datetime import timedelta
        
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(
            data={"sub": user.username, "user_id": user.id},
            expires_delta=access_token_expires
        )
        
        # Save session data including the access token
        import json
        temp_file = f"/tmp/stout_setup_{pin_id_int}.json"
        with open(temp_file, "w") as f:
            json.dump({
                "auth_token": auth_token,
                "user_info": user_info,
                "servers": servers,
                "access_token": access_token,  # Add the access token
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "full_name": user.full_name,
                    "is_admin": user.is_admin
                }
            }, f)

        # Clean up PIN store since done
        del pin_store[pin_id_int]

        # Redirect to next step (success)
        return RedirectResponse(
            url=f"/setup?step=1.5&session_id={pin_id_int}",
            status_code=303
        )

    except ValueError as e:
        print(f"Plex service error for PIN {pin_id_int}: {str(e)}")
        # Return pending status if it's a network error
        return JSONResponse(
            content={"status": "pending", "pin_id": pin_id_int, "error": str(e)}, 
            status_code=200,
            headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        print(f"Unexpected error verifying Plex PIN {pin_id_int}: {str(e)}")
        # Unexpected error - redirect with error message
        return RedirectResponse(
            url=f"/setup?step=1&error=OAuth verification failed: {str(e)}",
            status_code=303
        )


@router.post("/select-server")
async def setup_select_server(
    session_id: str = Form(...),
    server_id: str = Form(...),
    session: Session = Depends(get_session)
):
    """Complete server selection and basic setup"""
    try:
        import json
        import os
        
        # Load setup session data
        temp_file = f"/tmp/stout_setup_{session_id}.json"
        if not os.path.exists(temp_file):
            return RedirectResponse(
                url="/setup?step=1&error=Setup session expired", 
                status_code=303
            )
        
        with open(temp_file, 'r') as f:
            setup_data = json.load(f)
        
        # Find selected server
        selected_server = None
        for server in setup_data['servers']:
            if server['clientIdentifier'] == server_id:
                selected_server = server
                break
        
        if not selected_server:
            return RedirectResponse(
                url=f"/setup?step=1.5&session_id={session_id}&error=Invalid server selection", 
                status_code=303
            )
        
        # Update settings with server info
        settings_data = {
            'plex_url': selected_server['scheme'] + '://' + selected_server['address'] + ':' + str(selected_server['port']),
            'plex_token': setup_data['auth_token'],
            'plex_client_id': 'stout-requests',
            'is_configured': True
        }
        
        # Pass the user ID to properly set configured_by
        user_id = setup_data['user']['id'] if 'user' in setup_data else None
        SettingsService.update_settings(session, settings_data, user_id)
        
        # Clean up temp file
        os.remove(temp_file)
        
        return RedirectResponse(url=build_app_url("/setup/auto-login"), status_code=303)
        
    except Exception as e:
        return RedirectResponse(
            url=f"/setup?step=1&error=Server selection failed: {str(e)}", 
            status_code=303
        )


@router.post("/step2")
async def setup_step2(
    request: Request,
    session: Session = Depends(get_session),
    
    # Optional Radarr/Sonarr settings
    radarr_url: str = Form(""),
    radarr_api_key: str = Form(""),
    sonarr_url: str = Form(""),
    sonarr_api_key: str = Form(""),
    
    # App settings
    app_name: str = Form("Stout Requests"),
    require_approval: bool = Form(True),
    max_requests_per_user: int = Form(10)
):
    """Complete step 2 of setup - optional configuration"""
    try:
        # Get current settings
        settings = SettingsService.get_settings(session)
        
        # Update with optional settings
        settings_data = {
            'radarr_url': radarr_url.strip() if radarr_url else None,
            'radarr_api_key': radarr_api_key.strip() if radarr_api_key else None,
            'sonarr_url': sonarr_url.strip() if sonarr_url else None,
            'sonarr_api_key': sonarr_api_key.strip() if sonarr_api_key else None,
            'app_name': app_name.strip(),
            'require_approval': require_approval,
            'max_requests_per_user': max_requests_per_user
        }
        
        SettingsService.update_settings(session, settings_data)
        
        return RedirectResponse(url=build_app_url("/setup/auto-login"), status_code=303)
        
    except Exception as e:
        return RedirectResponse(
            url=f"/setup?step=2&error=Configuration failed: {str(e)}", 
            status_code=303
        )


@router.get("/complete")
async def setup_complete(
    request: Request,
    session: Session = Depends(get_session)
):
    """Setup completion page"""
    settings = SettingsService.get_settings(session)
    
    # Use global template context for consistent base_url handling
    from ..core.template_context import get_global_template_context
    global_context = get_global_template_context()
    
    context = {
        "request": request,
        "settings": settings,
        **global_context  # Include global context (base_url, etc.)
    }
    
    return templates.TemplateResponse("setup_complete.html", context)


@router.post("/test-plex")
async def test_plex_connection(
    plex_url: str = Form(...),
    plex_token: str = Form(...)
):
    """Test Plex connection during setup"""
    try:
        import requests
        
        response = requests.get(
            f"{plex_url.rstrip('/')}/identity",
            headers={'X-Plex-Token': plex_token},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "success", 
                "message": f"Connected to Plex server: {data.get('MediaContainer', {}).get('friendlyName', 'Unknown')}"
            }
        else:
            return {
                "status": "error", 
                "message": f"Failed to connect: HTTP {response.status_code}"
            }
            
    except Exception as e:
        return {
            "status": "error", 
            "message": f"Connection failed: {str(e)}"
        }


@router.get("/get-servers")
async def get_servers(
    session_id: str,
    request: Request,
    session: Session = Depends(get_session)
):
    """Get servers for selection during setup"""
    try:
        import json
        import os
        
        # Load setup session data
        temp_file = f"/tmp/stout_setup_{session_id}.json"
        if not os.path.exists(temp_file):
            return HTMLResponse('<div class="text-red-600 text-center">Setup session expired</div>')
        
        with open(temp_file, 'r') as f:
            setup_data = json.load(f)
        
        servers = setup_data.get('servers', [])
        
        # Get base_url for the response
        base_url = SettingsService.get_base_url(session)
        
        if not servers:
            return HTMLResponse(f'''
                <div class="text-center py-4">
                    <p class="text-gray-500">No Plex servers found for your account</p>
                    <a href="{base_url}/setup?step=1" class="mt-2 inline-block text-orange-600 hover:text-orange-800">Try again</a>
                </div>
            ''')
        
        # Render server selection HTML
        html = '<div class="space-y-3">'
        for server in servers:
            connection_type = "🏠 Local" if server.get('local') else "🌍 Remote"
            if server.get('relay'):
                connection_type += " (Relay)"
                
            html += f'''
                <label class="flex items-center p-4 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50">
                    <input type="radio" name="server_id" value="{server['clientIdentifier']}" required 
                           class="h-4 w-4 text-orange-600 focus:ring-orange-500 border-gray-300">
                    <div class="ml-3 flex-1">
                        <div class="flex items-center justify-between">
                            <h4 class="text-sm font-medium text-gray-900">{server['name']}</h4>
                            <span class="text-xs text-gray-500">{connection_type}</span>
                        </div>
                        <p class="text-xs text-gray-500">{server['address']}:{server['port']}</p>
                        <p class="text-xs text-gray-400">{server['platform']} • {server.get('productVersion', 'Unknown version')}</p>
                    </div>
                </label>
            '''
        html += '</div>'
        
        return HTMLResponse(html)
        
    except Exception as e:
        return HTMLResponse(f'<div class="text-red-600 text-center">Error loading servers: {str(e)}</div>')


@router.post("/test-tmdb")
async def test_tmdb_connection(
    tmdb_api_key: str = Form(...)
):
    """Test TMDB connection during setup"""
    try:
        import requests
        
        response = requests.get(
            "https://api.themoviedb.org/3/configuration",
            params={'api_key': tmdb_api_key},
            timeout=10
        )
        
        if response.status_code == 200:
            return {
                "status": "success", 
                "message": "TMDB API key is valid"
            }
        else:
            return {
                "status": "error", 
                "message": f"Invalid API key: HTTP {response.status_code}"
            }
            
    except Exception as e:
        return {
            "status": "error", 
            "message": f"Connection failed: {str(e)}"
        }

@router.get("/plex-oauth/status/{pin_id}", response_class=HTMLResponse)
async def check_plex_oauth_status(pin_id: int):
    from ..services.plex_service import PlexService
    plex_service = PlexService(setup_mode=True)

    token = plex_service.check_pin_status(pin_id)
    if token:
        # Optional: save the token to DB if you want
        return HTMLResponse("<strong>✅ Plex login successful!</strong>")
    return HTMLResponse("Still waiting for login...")

@router.get("/auto-login")
async def setup_auto_login(request: Request, session: Session = Depends(get_session)):
    """Automatically log in the user after setup completion"""
    try:
        # Find the user that was created during setup (should be the only admin)
        from ..models.user import User
        from sqlmodel import select
        
        statement = select(User).where(User.is_admin == True).order_by(User.id)
        admin_user = session.exec(statement).first()
        
        if not admin_user:
            # No admin user found - redirect to login
            return RedirectResponse(url=build_app_url("/login"), status_code=303)
        
        # Generate access token
        from ..core.auth import create_access_token
        from ..core.config import settings
        from datetime import timedelta
        
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(
            data={"sub": admin_user.username, "user_id": admin_user.id},
            expires_delta=access_token_expires
        )
        
        # Create response and set auth cookie (not httponly so JS can read it)
        response = RedirectResponse(url=build_app_url("/?setup_complete=true"), status_code=303)
        response.set_cookie(
            key="access_token",
            value=access_token,
            max_age=86400,  # 24 hours
            httponly=False,  # Allow JavaScript access for HTMX headers
            secure=False,  # Set to True in production with HTTPS
            path="/",
            samesite="lax"
        )
        
        return response
        
    except Exception as e:
        print(f"Error in auto-login: {e}")
        return RedirectResponse(url=build_app_url("/login"), status_code=303)

@router.get("/test-oauth")
async def test_oauth_flow():
    """Test endpoint to verify OAuth functionality"""
    try:
        from ..services.plex_service import PlexService
        plex_service = PlexService(setup_mode=True)
        
        # Generate a test PIN
        auth_data = plex_service.get_auth_url()
        
        return {
            "status": "success",
            "message": "OAuth flow is working correctly",
            "test_data": {
                "pin_id": auth_data["pin_id"],
                "auth_url": auth_data["auth_url"],
                "code": auth_data["code"]
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"OAuth flow failed: {str(e)}"
        }