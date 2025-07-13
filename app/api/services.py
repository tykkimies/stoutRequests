from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from typing import Optional, List
from datetime import datetime

from ..core.database import get_session
from ..models.user import User
from ..models.service_instance import ServiceInstance, ServiceType, RADARR_DEFAULT_SETTINGS, SONARR_DEFAULT_SETTINGS
from ..api.auth import get_current_admin_user_flexible
from ..services.settings_service import SettingsService
from ..core.template_context import get_global_template_context

router = APIRouter(prefix="/admin/services", tags=["admin-services"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/instances")
async def get_service_instances(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get all service instances"""
    statement = select(ServiceInstance).order_by(ServiceInstance.service_type, ServiceInstance.name)
    instances = session.exec(statement).all()
    
    # Content negotiation
    if request.headers.get("HX-Request"):
        # HTMX web client - return HTML fragment
        # Add test results to instances for display
        instances_with_tests = []
        for instance in instances:
            instance_dict = instance.mask_sensitive_data()
            # Convert datetime objects to strings for template
            if instance_dict.get('created_at'):
                instance_dict['created_at'] = instance_dict['created_at']
            if instance_dict.get('updated_at'):
                instance_dict['updated_at'] = instance_dict['updated_at'] 
            if instance_dict.get('last_tested_at'):
                instance_dict['last_tested_at'] = instance_dict['last_tested_at']
            # Convert enum to string for template
            if 'service_type' in instance_dict:
                instance_dict['service_type'] = instance_dict['service_type'].value if hasattr(instance_dict['service_type'], 'value') else str(instance_dict['service_type'])
            # Parse settings JSON string to dict for template
            if instance_dict.get('settings'):
                import json
                try:
                    instance_dict['settings'] = json.loads(instance_dict['settings'])
                except (json.JSONDecodeError, TypeError):
                    instance_dict['settings'] = {}
            else:
                instance_dict['settings'] = {}
            instance_dict['last_test_result'] = instance.get_test_result()
            instances_with_tests.append(instance_dict)
        
        # Create template response with global context
        global_context = get_global_template_context()
        context = {**global_context, "request": request, "instances": instances_with_tests}
        return templates.TemplateResponse("admin_services_list.html", context)
    else:
        # API client - return JSON with proper serialization
        masked_instances = []
        for instance in instances:
            instance_data = instance.mask_sensitive_data()
            # Convert datetime objects to strings
            if instance_data.get('created_at'):
                instance_data['created_at'] = instance_data['created_at'].isoformat()
            if instance_data.get('updated_at'):
                instance_data['updated_at'] = instance_data['updated_at'].isoformat()
            if instance_data.get('last_tested_at'):
                instance_data['last_tested_at'] = instance_data['last_tested_at'].isoformat()
            # Convert enum to string
            if 'service_type' in instance_data:
                instance_data['service_type'] = str(instance_data['service_type'])
            masked_instances.append(instance_data)
        return {"instances": masked_instances}


@router.post("/instances")
async def create_service_instance(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Create a new service instance"""
    try:
        data = await request.json()
        
        # Validate required fields
        required_fields = ['name', 'service_type', 'api_key']
        for field in required_fields:
            if not data.get(field):
                raise HTTPException(status_code=400, detail=f"{field} is required")
        
        # Validate connection info - either URL or hostname/port
        if not data.get('url') and not (data.get('hostname') and data.get('port')):
            raise HTTPException(status_code=400, detail="Either URL or hostname+port is required")
        
        # Validate service type
        try:
            service_type = ServiceType(data['service_type'])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid service type")
        
        # Check if name already exists for this service type
        existing = session.exec(
            select(ServiceInstance).where(
                ServiceInstance.name == data['name'],
                ServiceInstance.service_type == service_type
            )
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=400, 
                detail=f"A {service_type} instance with name '{data['name']}' already exists"
            )
        
        # Build URL if hostname/port provided, otherwise use URL field
        if data.get('hostname') and data.get('port'):
            use_ssl = data.get('use_ssl') == 'true' or data.get('use_ssl') is True
            protocol = 'https' if use_ssl else 'http'
            url = f"{protocol}://{data['hostname']}:{data['port']}"
        else:
            url = data['url'].rstrip('/')  # Remove trailing slash
        
        # Create the instance
        instance = ServiceInstance(
            name=data['name'],
            service_type=service_type,
            url=url,
            api_key=data['api_key'],
            is_enabled=data.get('is_enabled', True),
            created_by=current_user.id,
            updated_at=datetime.utcnow()
        )
        
        # Set default settings based on service type
        if service_type == ServiceType.RADARR:
            instance.set_settings(RADARR_DEFAULT_SETTINGS.copy())
        elif service_type == ServiceType.SONARR:
            instance.set_settings(SONARR_DEFAULT_SETTINGS.copy())
        
        # Override with provided settings
        if data.get('settings'):
            current_settings = instance.get_settings()
            current_settings.update(data['settings'])
            instance.set_settings(current_settings)
        
        session.add(instance)
        session.commit()
        session.refresh(instance)
        
        # Test the connection
        test_result = instance.test_connection()
        session.add(instance)  # Save test result
        session.commit()
        
        return {
            "message": f"{service_type.title()} instance '{data['name']}' created successfully",
            "instance": instance.mask_sensitive_data(),
            "test_result": test_result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating service instance: {e}")
        raise HTTPException(status_code=500, detail="Failed to create service instance")


@router.put("/instances/{instance_id}")
async def update_service_instance(
    instance_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Update a service instance"""
    try:
        instance = session.get(ServiceInstance, instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Service instance not found")
        
        data = await request.json()
        
        # Update fields if provided
        if 'name' in data:
            # Check for name conflicts (excluding current instance)
            existing = session.exec(
                select(ServiceInstance).where(
                    ServiceInstance.name == data['name'],
                    ServiceInstance.service_type == instance.service_type,
                    ServiceInstance.id != instance_id
                )
            ).first()
            
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail=f"A {instance.service_type} instance with name '{data['name']}' already exists"
                )
            instance.name = data['name']
        
        if 'url' in data:
            instance.url = data['url'].rstrip('/')
        
        if 'api_key' in data and data['api_key']:  # Only update if API key is provided
            instance.api_key = data['api_key']
        
        if 'is_enabled' in data:
            instance.is_enabled = data['is_enabled']
        
        if 'settings' in data:
            current_settings = instance.get_settings()
            current_settings.update(data['settings'])
            instance.set_settings(current_settings)
        
        instance.updated_at = datetime.utcnow()
        
        session.add(instance)
        session.commit()
        session.refresh(instance)
        
        return {
            "message": f"Service instance '{instance.name}' updated successfully",
            "instance": instance.mask_sensitive_data()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating service instance: {e}")
        raise HTTPException(status_code=500, detail="Failed to update service instance")


@router.delete("/instances/{instance_id}")
async def delete_service_instance(
    instance_id: int,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Delete a service instance"""
    instance = session.get(ServiceInstance, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Service instance not found")
    
    instance_name = instance.name
    session.delete(instance)
    session.commit()
    
    return {"message": f"Service instance '{instance_name}' deleted successfully"}


@router.post("/instances/{instance_id}/test")
async def test_service_instance(
    instance_id: int,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Test connection to a service instance"""
    instance = session.get(ServiceInstance, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Service instance not found")
    
    test_result = instance.test_connection()
    session.add(instance)  # Save test result
    session.commit()
    
    return {
        "instance_name": instance.name,
        "test_result": test_result
    }


@router.get("/instances/{instance_id}/quality-profiles")
async def get_quality_profiles(
    instance_id: int,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get quality profiles from a service instance"""
    instance = session.get(ServiceInstance, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Service instance not found")
    
    if not instance.is_enabled:
        raise HTTPException(status_code=400, detail="Service instance is disabled")
    
    profiles = await instance.get_quality_profiles()
    return {"quality_profiles": profiles}


@router.get("/instances/{instance_id}/root-folders")
async def get_root_folders(
    instance_id: int,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get root folders from a service instance"""
    instance = session.get(ServiceInstance, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Service instance not found")
    
    if not instance.is_enabled:
        raise HTTPException(status_code=400, detail="Service instance is disabled")
    
    folders = await instance.get_root_folders()
    return {"root_folders": folders}


@router.get("/instances/{instance_id}/tags")
async def get_tags(
    instance_id: int,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Get tags from a service instance"""
    instance = session.get(ServiceInstance, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Service instance not found")
    
    if not instance.is_enabled:
        raise HTTPException(status_code=400, detail="Service instance is disabled")
    
    tags = await instance.get_tags()
    return {"tags": tags}


@router.post("/instances/{instance_id}/toggle")
async def toggle_service_instance(
    instance_id: int,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Toggle enable/disable status of a service instance"""
    instance = session.get(ServiceInstance, instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Service instance not found")
    
    instance.is_enabled = not instance.is_enabled
    instance.updated_at = datetime.utcnow()
    
    session.add(instance)
    session.commit()
    
    status = "enabled" if instance.is_enabled else "disabled"
    return {
        "message": f"Service instance '{instance.name}' {status}",
        "is_enabled": instance.is_enabled
    }


@router.post("/test-connection")
async def test_service_connection(
    request: Request,
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Test service connection without creating an instance"""
    try:
        data = await request.json()
        
        # Validate required fields
        required_fields = ['service_type', 'api_key']
        for field in required_fields:
            if not data.get(field):
                raise HTTPException(status_code=400, detail=f"{field} is required")
        
        # Validate connection info
        if not (data.get('hostname') and data.get('port')):
            raise HTTPException(status_code=400, detail="hostname and port are required")
        
        # Create a temporary service instance for testing (not saved to DB)
        from ..models.service_instance import ServiceInstance, ServiceType
        service_type = ServiceType(data['service_type'])
        
        # Build URL from components
        use_ssl = data.get('use_ssl') == 'true' or data.get('use_ssl') is True
        protocol = 'https' if use_ssl else 'http'
        url = f"{protocol}://{data['hostname']}:{data['port']}"
        
        temp_instance = ServiceInstance(
            name="temp-test",
            service_type=service_type,
            url=url,
            api_key=data['api_key']
        )
        
        # Set connection settings
        settings = {
            'hostname': data['hostname'],
            'port': int(data['port']),
            'use_ssl': use_ssl,
            'base_url': data.get('base_url', '')
        }
        temp_instance.set_settings(settings)
        
        # Test the connection
        test_result = temp_instance.test_connection()
        
        response_data = {
            "test_result": test_result,
            "message": "Connection test completed"
        }
        
        # If connection successful, also fetch available options
        if test_result.get('status') == 'connected':
            try:
                # Get quality profiles
                quality_profiles = await temp_instance.get_quality_profiles()
                response_data['quality_profiles'] = quality_profiles
                
                # Get root folders
                root_folders = await temp_instance.get_root_folders()
                response_data['root_folders'] = root_folders
                
                # Get tags
                tags = await temp_instance.get_tags()
                response_data['tags'] = tags
                
            except Exception as e:
                print(f"Warning: Could not fetch service options: {e}")
                # Don't fail the whole request if optional data fails
                response_data['quality_profiles'] = []
                response_data['root_folders'] = []
                response_data['tags'] = []
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error testing connection: {e}")
        raise HTTPException(status_code=500, detail="Failed to test connection")


@router.get("/migrate-legacy")
async def migrate_legacy_services(
    current_user: User = Depends(get_current_admin_user_flexible),
    session: Session = Depends(get_session)
):
    """Migrate legacy Radarr/Sonarr settings to new service instances"""
    try:
        # Get current settings
        settings = SettingsService.get_settings(session)
        migrated_count = 0
        
        # Migrate Radarr if configured
        if settings.radarr_url and settings.radarr_api_key:
            # Check if already migrated
            existing = session.exec(
                select(ServiceInstance).where(
                    ServiceInstance.service_type == ServiceType.RADARR,
                    ServiceInstance.url == settings.radarr_url.rstrip('/')
                )
            ).first()
            
            if not existing:
                radarr_instance = ServiceInstance(
                    name="Radarr (Legacy)",
                    service_type=ServiceType.RADARR,
                    url=settings.radarr_url.rstrip('/'),
                    api_key=settings.radarr_api_key,
                    is_enabled=True,
                    created_by=current_user.id,
                    updated_at=datetime.utcnow()
                )
                radarr_instance.set_settings(RADARR_DEFAULT_SETTINGS.copy())
                
                session.add(radarr_instance)
                migrated_count += 1
        
        # Migrate Sonarr if configured
        if settings.sonarr_url and settings.sonarr_api_key:
            # Check if already migrated
            existing = session.exec(
                select(ServiceInstance).where(
                    ServiceInstance.service_type == ServiceType.SONARR,
                    ServiceInstance.url == settings.sonarr_url.rstrip('/')
                )
            ).first()
            
            if not existing:
                sonarr_instance = ServiceInstance(
                    name="Sonarr (Legacy)",
                    service_type=ServiceType.SONARR,
                    url=settings.sonarr_url.rstrip('/'),
                    api_key=settings.sonarr_api_key,
                    is_enabled=True,
                    created_by=current_user.id,
                    updated_at=datetime.utcnow()
                )
                sonarr_instance.set_settings(SONARR_DEFAULT_SETTINGS.copy())
                
                session.add(sonarr_instance)
                migrated_count += 1
        
        if migrated_count > 0:
            session.commit()
        
        return {
            "message": f"Migration completed. {migrated_count} legacy services migrated to new format.",
            "migrated_count": migrated_count
        }
        
    except Exception as e:
        print(f"Error migrating legacy services: {e}")
        raise HTTPException(status_code=500, detail="Failed to migrate legacy services")