from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from typing import Optional
from datetime import datetime

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
    # Debug logging for setup wizard access
    step = request.query_params.get("step", "1")
    session_id = request.query_params.get("session_id", "none")
    print(f"🔧 Setup wizard accessed: step={step}, session_id={session_id}, url={request.url}")
    
    # Check if already configured
    is_configured = SettingsService.is_configured(session)
    print(f"🔧 Setup wizard is_configured check: {is_configured}")
    
    if is_configured:
        print(f"🔧 Setup wizard redirecting to main site because is_configured=True")
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
    
    print(f"🔧 Setup wizard rendering step {context['step']} with has_users={has_users}")
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
    request: Request,
    session: Session = Depends(get_session)
):
    """Complete server selection and library preferences, then proceed to step 2 configuration"""
    try:
        # Get form data
        form_data = await request.form()
        session_id = form_data.get('session_id')
        server_id = form_data.get('server_id')
        selected_libraries = form_data.getlist('selected_libraries')
        
        print(f"🔧 Setup select-server called: session_id={session_id}, server_id={server_id}, libraries={selected_libraries}")
        
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
        
        # Update settings with server info (don't mark as configured yet - wait for step 2)
        settings_data = {
            'plex_url': selected_server['scheme'] + '://' + selected_server['address'] + ':' + str(selected_server['port']),
            'plex_token': setup_data['auth_token'],
            'plex_client_id': 'stout-requests',
            'is_configured': False  # Don't mark as configured until step 2 is complete
        }
        
        # Pass the user ID to properly set configured_by
        user_id = setup_data['user']['id'] if 'user' in setup_data else None
        SettingsService.update_settings(session, settings_data, user_id)
        
        # Save library preferences to setup data for later use
        setup_data['selected_libraries'] = selected_libraries
        with open(temp_file, 'w') as f:
            json.dump(setup_data, f)
        
        redirect_url = build_app_url(f"/setup?step=2&session_id={session_id}")
        print(f"🔧 Setup select-server redirecting to: {redirect_url}")
        return RedirectResponse(url=redirect_url, status_code=303)
        
    except Exception as e:
        return RedirectResponse(
            url=f"/setup?step=1&error=Server selection failed: {str(e)}", 
            status_code=303
        )


@router.post("/select-server-skip")
async def setup_select_server_skip(
    request: Request,
    session: Session = Depends(get_session)
):
    """Complete server selection and library preferences, skip configuration and go to sync step"""
    try:
        # Get form data
        form_data = await request.form()
        session_id = form_data.get('session_id')
        server_id = form_data.get('server_id')
        selected_libraries = form_data.getlist('selected_libraries')
        
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
        
        # Update settings with server info but don't mark as configured yet
        settings_data = {
            'plex_url': selected_server['scheme'] + '://' + selected_server['address'] + ':' + str(selected_server['port']),
            'plex_token': setup_data['auth_token'],
            'plex_client_id': 'stout-requests',
            'is_configured': False  # Don't mark as configured until sync step completes
        }
        
        # Pass the user ID to properly set configured_by
        user_id = setup_data['user']['id'] if 'user' in setup_data else None
        SettingsService.update_settings(session, settings_data, user_id)
        
        # Save library preferences for the sync step
        if selected_libraries:
            settings = SettingsService.get_settings(session)
            settings.set_sync_library_preferences(selected_libraries)
            settings.updated_at = datetime.utcnow()
            session.add(settings)
            session.commit()
        
        # Save library preferences to setup data for the sync step
        setup_data['selected_libraries'] = selected_libraries
        with open(temp_file, 'w') as f:
            json.dump(setup_data, f)
        
        # Go directly to sync step instead of auto-login
        return RedirectResponse(url=build_app_url(f"/setup?step=3&session_id={session_id}"), status_code=303)
        
    except Exception as e:
        return RedirectResponse(
            url=f"/setup?step=1&error=Server selection failed: {str(e)}", 
            status_code=303
        )


@router.post("/step2")
async def setup_step2(
    request: Request,
    session: Session = Depends(get_session),
    
    # Session ID (optional - only present when coming from step 1.5)
    session_id: str = Form(""),
    
    # Radarr settings - full form fields
    radarr_name: str = Form(""),
    radarr_hostname: str = Form(""),
    radarr_port: int = Form(7878),
    radarr_use_ssl: bool = Form(False),
    radarr_api_key: str = Form(""),
    radarr_base_url: str = Form(""),
    radarr_quality_profile_id: Optional[int] = Form(None),
    radarr_root_folder_path: str = Form(""),
    radarr_minimum_availability: str = Form("released"),
    radarr_tags: str = Form(""),
    radarr_is_default_movie: bool = Form(True),
    radarr_is_4k_default: bool = Form(False),
    radarr_enable_scan: bool = Form(True),
    radarr_enable_automatic_search: bool = Form(True),
    radarr_enable_integration: bool = Form(True),
    
    # Sonarr settings - full form fields
    sonarr_name: str = Form(""),
    sonarr_hostname: str = Form(""),
    sonarr_port: int = Form(8989),
    sonarr_use_ssl: bool = Form(False),
    sonarr_api_key: str = Form(""),
    sonarr_base_url: str = Form(""),
    sonarr_quality_profile_id: Optional[int] = Form(None),
    sonarr_root_folder_path: str = Form(""),
    sonarr_language_profile_id: Optional[int] = Form(None),
    sonarr_tags: str = Form(""),
    sonarr_is_default_tv: bool = Form(True),
    sonarr_is_4k_default: bool = Form(False),
    sonarr_enable_scan: bool = Form(True),
    sonarr_enable_automatic_search: bool = Form(True),
    sonarr_enable_integration: bool = Form(True),
    sonarr_enable_season_folders: bool = Form(True),
    sonarr_anime_standard_format: bool = Form(False),
    
    # App settings
    app_name: str = Form("CuePlex"),
    require_approval: bool = Form(True),
    max_requests_per_user: int = Form(10)
):
    """Complete step 2 of setup - optional configuration"""
    try:
        print(f"🔧 Setup step2 called with radarr_hostname='{radarr_hostname}', sonarr_hostname='{sonarr_hostname}'")
        # Get current settings
        settings = SettingsService.get_settings(session)
        
        # Update app settings (non-service related) but don't mark setup as complete yet
        settings_data = {
            'app_name': app_name.strip(),
            'require_approval': require_approval,
            'max_requests_per_user': max_requests_per_user,
            'is_configured': False  # Don't mark as configured until sync step completes
        }
        
        SettingsService.update_settings(session, settings_data)
        
        # Create ServiceInstance objects for Radarr and Sonarr if provided
        from ..models.service_instance import ServiceInstance, ServiceType, RADARR_DEFAULT_SETTINGS, SONARR_DEFAULT_SETTINGS
        from ..models.user import User
        
        # Get the first admin user (server owner) to assign as creator
        first_admin = session.exec(select(User).where(User.is_admin == True)).first()
        created_by = first_admin.id if first_admin else None
        
        # Create Radarr instance if configured
        if radarr_hostname.strip() and radarr_api_key.strip():
            print(f"🔧 Creating Radarr instance: {radarr_name} at {radarr_hostname}:{radarr_port}")
            # Build URL from components
            protocol = "https" if radarr_use_ssl else "http"
            base = f"/{radarr_base_url.strip('/')}" if radarr_base_url.strip() else ""
            url = f"{protocol}://{radarr_hostname.strip()}:{radarr_port}{base}"
            
            # Build settings (same as admin form)
            radarr_settings = RADARR_DEFAULT_SETTINGS.copy()
            radarr_settings.update({
                "hostname": radarr_hostname.strip(),
                "port": int(radarr_port),
                "use_ssl": radarr_use_ssl,
                "base_url": radarr_base_url.strip() if radarr_base_url.strip() else None,
                "quality_profile_id": int(radarr_quality_profile_id) if radarr_quality_profile_id else None,
                "root_folder_path": radarr_root_folder_path or None,
                "minimum_availability": radarr_minimum_availability,
                "tags": [tag.strip() for tag in radarr_tags.split(",") if tag.strip()] if radarr_tags else [],
                "monitored": radarr_enable_automatic_search,
                "search_for_movie": radarr_enable_automatic_search,
                "enable_scan": radarr_enable_scan,
                "enable_automatic_search": radarr_enable_automatic_search,
                "enable_integration": radarr_enable_integration
            })
            
            radarr_instance = ServiceInstance(
                name=radarr_name.strip() if radarr_name.strip() else "Radarr",
                service_type=ServiceType.RADARR,
                url=url,  # Built URL for compatibility
                api_key=radarr_api_key.strip(),
                is_enabled=True,
                is_default_movie=radarr_is_default_movie,
                is_4k_default=radarr_is_4k_default,
                created_by=created_by
            )
            radarr_instance.set_settings(radarr_settings)
            session.add(radarr_instance)
            print(f"🔧 Radarr instance added to session: {radarr_instance.name}")
        
        # Create Sonarr instance if configured
        if sonarr_hostname.strip() and sonarr_api_key.strip():
            # Build URL from components
            protocol = "https" if sonarr_use_ssl else "http"
            base = f"/{sonarr_base_url.strip('/')}" if sonarr_base_url.strip() else ""
            url = f"{protocol}://{sonarr_hostname.strip()}:{sonarr_port}{base}"
            
            # Build settings (same as admin form)
            sonarr_settings = SONARR_DEFAULT_SETTINGS.copy()
            sonarr_settings.update({
                "hostname": sonarr_hostname.strip(),
                "port": int(sonarr_port),
                "use_ssl": sonarr_use_ssl,
                "base_url": sonarr_base_url.strip() if sonarr_base_url.strip() else None,
                "quality_profile_id": int(sonarr_quality_profile_id) if sonarr_quality_profile_id else None,
                "language_profile_id": int(sonarr_language_profile_id) if sonarr_language_profile_id else None,
                "root_folder_path": sonarr_root_folder_path or None,
                "tags": [tag.strip() for tag in sonarr_tags.split(",") if tag.strip()] if sonarr_tags else [],
                "enable_scan": sonarr_enable_scan,
                "enable_automatic_search": sonarr_enable_automatic_search,
                "enable_integration": sonarr_enable_integration,
                "season_folder": sonarr_enable_season_folders,
                "anime_standard_format": sonarr_anime_standard_format
            })
            
            sonarr_instance = ServiceInstance(
                name=sonarr_name.strip() if sonarr_name.strip() else "Sonarr",
                service_type=ServiceType.SONARR,
                url=url,  # Built URL for compatibility
                api_key=sonarr_api_key.strip(),
                is_enabled=True,
                is_default_tv=sonarr_is_default_tv,
                is_4k_default=sonarr_is_4k_default,
                created_by=created_by
            )
            sonarr_instance.set_settings(sonarr_settings)
            session.add(sonarr_instance)
        
        print(f"🔧 Committing setup step2 changes to database")
        session.commit()
        print(f"🔧 Setup step2 completed successfully")
        
        # Save library preferences from setup data if available
        if session_id.strip():
            import os
            temp_file = f"/tmp/stout_setup_{session_id}.json"
            if os.path.exists(temp_file):
                try:
                    import json
                    with open(temp_file, 'r') as f:
                        setup_data = json.load(f)
                    
                    # Save library preferences if they exist
                    selected_libraries = setup_data.get('selected_libraries', [])
                    if selected_libraries:
                        print(f"🔧 Saving library preferences: {selected_libraries}")
                        settings = SettingsService.get_settings(session)
                        settings.set_sync_library_preferences(selected_libraries)
                        settings.updated_at = datetime.utcnow()
                        session.add(settings)
                        session.commit()
                        print(f"🔧 Library preferences saved successfully")
                    
                    # Don't clean up temp file yet - we need it for sync step
                    print(f"🔧 Keeping temp file for sync step: {temp_file}")
                except Exception as lib_error:
                    print(f"🔧 Warning: Could not save library preferences: {lib_error}")
        
        # Redirect to sync step instead of auto-login
        print(f"🔧 Redirecting to sync step with session_id='{session_id}'")
        if session_id.strip():
            return RedirectResponse(url=build_app_url(f"/setup?step=3&session_id={session_id}"), status_code=303)
        else:
            return RedirectResponse(url=build_app_url("/setup?step=3"), status_code=303)
        
    except Exception as e:
        print(f"🔧 ERROR in setup step2: {str(e)}")
        import traceback
        traceback.print_exc()
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


@router.post("/test-radarr")
async def test_radarr_connection(
    radarr_hostname: str = Form(...),
    radarr_port: str = Form("7878"),
    use_ssl: bool = Form(False),
    radarr_api_key: str = Form(...),
    radarr_base_url: str = Form("")
):
    """Test Radarr connection during setup and return folders/profiles"""
    try:
        from ..services.radarr_service import RadarrService
        import requests
        
        # Build URL
        protocol = "https" if use_ssl else "http"
        base = f"/{radarr_base_url.strip('/')}" if radarr_base_url.strip() else ""
        url = f"{protocol}://{radarr_hostname}:{radarr_port}{base}"
        
        # Test basic connection
        response = requests.get(
            f"{url}/api/v3/system/status",
            headers={'X-Api-Key': radarr_api_key},
            timeout=10
        )
        
        if response.status_code != 200:
            return {
                "status": "error", 
                "message": f"Failed to connect: HTTP {response.status_code}"
            }
        
        status_data = response.json()
        
        # Get folders and quality profiles
        folders = []
        quality_profiles = []
        
        try:
            # Get root folders
            folders_response = requests.get(
                f"{url}/api/v3/rootfolder",
                headers={'X-Api-Key': radarr_api_key},
                timeout=10
            )
            if folders_response.status_code == 200:
                folders = folders_response.json()
        except:
            pass
        
        try:
            # Get quality profiles
            profiles_response = requests.get(
                f"{url}/api/v3/qualityprofile",
                headers={'X-Api-Key': radarr_api_key},
                timeout=10
            )
            if profiles_response.status_code == 200:
                quality_profiles = profiles_response.json()
        except:
            pass
        
        return {
            "status": "success", 
            "message": f"Connected to Radarr: {status_data.get('appName', 'Unknown')} v{status_data.get('version', 'Unknown')}",
            "folders": folders,
            "quality_profiles": quality_profiles
        }
            
    except Exception as e:
        return {
            "status": "error", 
            "message": f"Connection failed: {str(e)}"
        }


@router.post("/test-sonarr")
async def test_sonarr_connection(
    sonarr_hostname: str = Form(...),
    sonarr_port: str = Form("8989"),
    use_ssl: bool = Form(False),
    sonarr_api_key: str = Form(...),
    sonarr_base_url: str = Form("")
):
    """Test Sonarr connection during setup and return folders/profiles"""
    try:
        from ..services.sonarr_service import SonarrService
        import requests
        
        # Build URL
        protocol = "https" if use_ssl else "http"
        base = f"/{sonarr_base_url.strip('/')}" if sonarr_base_url.strip() else ""
        url = f"{protocol}://{sonarr_hostname}:{sonarr_port}{base}"
        
        # Test basic connection
        response = requests.get(
            f"{url}/api/v3/system/status",
            headers={'X-Api-Key': sonarr_api_key},
            timeout=10
        )
        
        if response.status_code != 200:
            return {
                "status": "error", 
                "message": f"Failed to connect: HTTP {response.status_code}"
            }
        
        status_data = response.json()
        
        # Get folders and quality profiles
        folders = []
        quality_profiles = []
        language_profiles = []
        
        try:
            # Get root folders
            folders_response = requests.get(
                f"{url}/api/v3/rootfolder",
                headers={'X-Api-Key': sonarr_api_key},
                timeout=10
            )
            if folders_response.status_code == 200:
                folders = folders_response.json()
        except:
            pass
        
        try:
            # Get quality profiles
            profiles_response = requests.get(
                f"{url}/api/v3/qualityprofile",
                headers={'X-Api-Key': sonarr_api_key},
                timeout=10
            )
            if profiles_response.status_code == 200:
                quality_profiles = profiles_response.json()
        except:
            pass
        
        try:
            # Get language profiles (Sonarr v3)
            lang_response = requests.get(
                f"{url}/api/v3/languageprofile",
                headers={'X-Api-Key': sonarr_api_key},
                timeout=10
            )
            if lang_response.status_code == 200:
                language_profiles = lang_response.json()
        except:
            # Try v4 endpoint
            try:
                lang_response = requests.get(
                    f"{url}/api/v4/language",
                    headers={'X-Api-Key': sonarr_api_key},
                    timeout=10
                )
                if lang_response.status_code == 200:
                    language_profiles = lang_response.json()
            except:
                pass
        
        return {
            "status": "success", 
            "message": f"Connected to Sonarr: {status_data.get('appName', 'Unknown')} v{status_data.get('version', 'Unknown')}",
            "folders": folders,
            "quality_profiles": quality_profiles,
            "language_profiles": language_profiles
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
        # Clean up any remaining temp files from query parameters
        session_id = request.query_params.get('session_id')
        if session_id:
            import os
            temp_file = f"/tmp/stout_setup_{session_id}.json"
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    print(f"🔧 Cleaned up temp file on auto-login: {temp_file}")
                except Exception as cleanup_error:
                    print(f"🔧 Warning: Could not clean up temp file: {cleanup_error}")
        
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
            max_age=86400,  # 24 hours to match token expiration
            httponly=False,  # Allow JavaScript access for HTMX headers
            secure=False,  # Set to True in production with HTTPS
            path="/",
            samesite="lax"
        )
        
        return response
        
    except Exception as e:
        print(f"Error in auto-login: {e}")
        return RedirectResponse(url=build_app_url("/login"), status_code=303)

@router.get("/get-libraries")
async def get_libraries(
    session_id: str,
    server_id: str,
    session: Session = Depends(get_session)
):
    """Get available libraries for the selected server during setup"""
    try:
        import json
        import os
        
        # Load setup session data
        temp_file = f"/tmp/stout_setup_{session_id}.json"
        if not os.path.exists(temp_file):
            raise HTTPException(status_code=400, detail="Setup session expired")
        
        with open(temp_file, 'r') as f:
            setup_data = json.load(f)
        
        # Find selected server
        selected_server = None
        for server in setup_data['servers']:
            if server['clientIdentifier'] == server_id:
                selected_server = server
                break
        
        if not selected_server:
            raise HTTPException(status_code=400, detail="Invalid server selection")
        
        # Temporarily configure Plex service with this server's info to get libraries
        plex_url = selected_server['scheme'] + '://' + selected_server['address'] + ':' + str(selected_server['port'])
        plex_token = setup_data['auth_token']
        
        # Create a temporary PlexService instance
        from ..services.plex_service import PlexService
        temp_plex_service = PlexService(session, setup_mode=True, override_url=plex_url, override_token=plex_token)
        
        # Get available libraries
        libraries = temp_plex_service.get_available_libraries()
        
        return {
            "libraries": libraries,
            "server_info": {
                "name": selected_server['name'],
                "address": selected_server['address']
            }
        }
        
    except Exception as e:
        print(f"❌ Error getting libraries for setup: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get libraries: {str(e)}")


@router.post("/sync")
async def setup_sync(
    request: Request,
    session_id: str = Form(...),
    session: Session = Depends(get_session)
):
    """Perform initial library sync during setup with real-time progress"""
    try:
        import json
        import os
        from fastapi.responses import StreamingResponse
        
        # Debug: Print request headers
        accept_header = request.headers.get("Accept", "")
        hx_request = request.headers.get("HX-Request", "")
        print(f"🔧 Sync request headers - Accept: '{accept_header}', HX-Request: '{hx_request}'")
        
        # Check for streaming request (either HTMX or SSE)
        is_streaming = request.headers.get("HX-Request") or "text/event-stream" in accept_header
        print(f"🔧 Is streaming request: {is_streaming}")
        
        if is_streaming:
            print(f"🔧 Taking streaming sync path")
            # Streaming request - return real-time progress updates
            return StreamingResponse(
                sync_with_progress(session_id, session),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache", 
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "*"
                }
            )
        else:
            print(f"🔧 Taking non-streaming sync path")
            # Regular request - perform sync and return result
            return await perform_sync(session_id, session)
    except Exception as e:
        print(f"🔧 ERROR in setup sync: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


async def sync_with_progress(session_id: str, session: Session):
    """Generator that yields real progress updates during sync"""
    try:
        import json
        import os
        from ..services.plex_sync_service import PlexSyncService
        from ..services.settings_service import SettingsService
        import asyncio
        
        print(f"🔧 [STREAMING] Generator started for session {session_id}")
        
        # Load setup session data
        temp_file = f"/tmp/stout_setup_{session_id}.json"
        if not os.path.exists(temp_file):
            yield f"data: {{\"error\": \"Setup session expired\", \"progress\": 0}}\n\n"
            return
        
        # Send initial progress
        yield f"data: {{\"progress\": 0, \"status\": \"Starting sync...\", \"movies\": 0, \"tv_shows\": 0}}\n\n"
        print(f"🔧 [STREAMING] Sent initial progress")
        
        # Perform actual sync using existing sync service
        sync_service = PlexSyncService(session)
        
        # Step-by-step progress updates
        yield f"data: {{\"progress\": 10, \"status\": \"Connecting to Plex...\", \"movies\": 0, \"tv_shows\": 0}}\n\n"
        await asyncio.sleep(0.1)
        
        yield f"data: {{\"progress\": 20, \"status\": \"Running library sync...\", \"movies\": 0, \"tv_shows\": 0}}\n\n"
        await asyncio.sleep(0.1)
        
        # Run the actual sync
        sync_result = await sync_service.sync_library()
        print(f"🔧 [STREAMING] Sync completed with result: {sync_result}")
        
        yield f"data: {{\"progress\": 90, \"status\": \"Finalizing...\", \"movies\": 0, \"tv_shows\": 0}}\n\n"
        await asyncio.sleep(0.1)
        
        # Get final counts
        from ..models.plex_library_item import PlexLibraryItem
        from sqlmodel import select, func
        
        movie_count = session.exec(
            select(func.count(PlexLibraryItem.id)).where(PlexLibraryItem.media_type == "movie")
        ).first() or 0
        
        tv_count = session.exec(
            select(func.count(PlexLibraryItem.id)).where(PlexLibraryItem.media_type == "tv")
        ).first() or 0
        
        print(f"🔧 [STREAMING] Final counts - Movies: {movie_count}, TV: {tv_count}")
        
        # Send completion with real counts
        completion_data = {
            "progress": 100,
            "status": "Sync completed successfully!",
            "movies": movie_count,
            "tv_shows": tv_count,
            "completed": True
        }
        final_data = f"data: {json.dumps(completion_data)}\n\n"
        print(f"🔧 [STREAMING] Sending completion: {final_data.strip()}")
        yield final_data
        
        # Mark setup as complete after successful sync
        settings = SettingsService.get_settings(session)
        settings_data = {'is_configured': True}
        SettingsService.update_settings(session, settings_data)
        print(f"🔧 [STREAMING] Setup marked as configured")
        
        # Start background job scheduler now that setup is complete
        try:
            from ..services.background_jobs import background_jobs
            if not background_jobs.scheduler_running:
                background_jobs.start()
                print(f"🚀 Background job scheduler started after setup completion")
        except Exception as e:
            print(f"⚠️ Error starting scheduler after setup: {e}")
        
        # Clean up temp file
        if os.path.exists(temp_file):
            os.remove(temp_file)
            print(f"🔧 [STREAMING] Cleaned up temp file")
        
        print(f"🔧 [STREAMING] Generator completed for session {session_id}")
        
    except Exception as e:
        print(f"🔧 [STREAMING] ERROR in streaming generator: {str(e)}")
        import traceback
        traceback.print_exc()
        yield f"data: {{\"progress\": 0, \"status\": \"Streaming failed: {str(e)}\", \"error\": true}}\n\n"


async def perform_sync(session_id: str, session: Session):
    """Perform sync and return final result"""
    try:
        import json
        import os
        
        # Load setup session data
        temp_file = f"/tmp/stout_setup_{session_id}.json"
        if not os.path.exists(temp_file):
            raise HTTPException(status_code=400, detail="Setup session expired")
        
        with open(temp_file, 'r') as f:
            setup_data = json.load(f)
        
        print(f"🔧 Starting non-streaming sync for session {session_id}")
        
        # Trigger sync using existing sync service
        from ..services.plex_sync_service import PlexSyncService
        sync_service = PlexSyncService(session)
        sync_result = await sync_service.sync_library()
        
        print(f"🔧 Non-streaming sync completed: {sync_result}")
        
        # Mark setup as complete after successful sync
        from ..services.settings_service import SettingsService
        settings = SettingsService.get_settings(session)
        settings_data = {'is_configured': True}
        SettingsService.update_settings(session, settings_data)
        print(f"🔧 Setup marked as configured after successful sync")
        
        # Start background job scheduler now that setup is complete
        try:
            from ..services.background_jobs import background_jobs
            if not background_jobs.scheduler_running:
                background_jobs.start()
                print(f"🚀 Background job scheduler started after setup completion")
        except Exception as e:
            print(f"⚠️ Error starting scheduler after setup: {e}")
        
        # Clean up temp file after successful sync
        if os.path.exists(temp_file):
            os.remove(temp_file)
            print(f"🔧 Cleaned up temp file: {temp_file}")
        
        return {
                "status": "success",
                "message": "Initial sync completed successfully",
                "sync_result": sync_result
            }
            
    except Exception as e:
        print(f"❌ Error during initial sync: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


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