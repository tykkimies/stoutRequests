"""
Multi-Instance Integration Service

Handles sending requests to appropriate Radarr/Sonarr instances based on:
- Service instance configuration
- Quality tier requirements
- 4K handling approach (dedicated vs profile-based)
"""

from typing import Optional, Dict, Any
from sqlmodel import Session
from app.models.service_instance import ServiceInstance, ServiceType
from app.models.media_request import MediaRequest, MediaType
from app.services.radarr_service import RadarrService
from app.services.sonarr_service import SonarrService
import asyncio

class MultiInstanceIntegrationService:
    """Service for integrating requests with appropriate Radarr/Sonarr instances"""
    
    def __init__(self, session: Session):
        self.session = session
    
    async def integrate_request(self, media_request: MediaRequest) -> Optional[Dict[str, Any]]:
        """
        Integrate a media request with the appropriate service instance
        
        Returns:
            Dict with integration result or None if failed
        """
        print(f"\n🎆 ===== MULTI-INSTANCE INTEGRATION SERVICE ===== 🎆")
        print(f"📊 Request ID: {media_request.id}")
        print(f"📊 Title: {media_request.title}")
        print(f"📊 Media Type: {media_request.media_type.value}")
        print(f"📊 TMDB ID: {media_request.tmdb_id}")
        print(f"📊 Service Instance ID: {media_request.service_instance_id}")
        
        if not media_request.service_instance_id:
            print(f"❌ INTEGRATION FAILED: No service instance specified for request {media_request.id}")
            return None
        
        print(f"🔍 Fetching service instance {media_request.service_instance_id} from database...")
        # Get the service instance
        service_instance = self.session.get(ServiceInstance, media_request.service_instance_id)
        
        if not service_instance:
            print(f"❌ INTEGRATION FAILED: Service instance {media_request.service_instance_id} not found in database")
            return None
            
        if not service_instance.is_enabled:
            print(f"❌ INTEGRATION FAILED: Service instance {media_request.service_instance_id} is disabled")
            print(f"📊 Instance Name: {service_instance.name}")
            print(f"📊 Instance Enabled: {service_instance.is_enabled}")
            return None
            
        print(f"✅ Service instance validation passed:")
        print(f"📊 Instance Name: {service_instance.name}")
        print(f"📊 Instance Type: {service_instance.service_type.value}")
        print(f"📊 Instance URL: {service_instance.url}")
        print(f"📊 Instance Category: {service_instance.instance_category}")
        print(f"📊 Instance Enabled: {service_instance.is_enabled}")
        print(f"📊 API Key Present: {'✅' if service_instance.api_key else '❌'}")
        if service_instance.api_key:
            print(f"📊 API Key Preview: {service_instance.api_key[:8]}***{service_instance.api_key[-4:] if len(service_instance.api_key) > 12 else '***'}")
        
        try:
            print(f"🖀 Routing to appropriate integration method...")
            
            if media_request.media_type == MediaType.MOVIE:
                print(f"🎬 Routing to movie integration (_integrate_movie_request)")
                result = await self._integrate_movie_request(media_request, service_instance)
                print(f"🎬 Movie integration result: {result}")
                return result
            elif media_request.media_type == MediaType.TV:
                print(f"📺 Routing to TV integration (_integrate_tv_request)")
                result = await self._integrate_tv_request(media_request, service_instance)
                print(f"📺 TV integration result: {result}")
                return result
            else:
                print(f"❌ INTEGRATION FAILED: Unsupported media type {media_request.media_type} for request {media_request.id}")
                return None
        except Exception as e:
            print(f"❌ INTEGRATION EXCEPTION: Error integrating request {media_request.id} with instance {service_instance.name}: {e}")
            import traceback
            print(f"🔍 Full stack trace from multi-instance integration:")
            traceback.print_exc()
            return None
    
    async def _integrate_movie_request(
        self, 
        media_request: MediaRequest, 
        service_instance: ServiceInstance
    ) -> Optional[Dict[str, Any]]:
        """Integrate movie request with Radarr instance"""
        
        print(f"\n🎬 ===== MOVIE INTEGRATION METHOD ===== 🎬")
        print(f"📊 Request: {media_request.title} (TMDB: {media_request.tmdb_id})")
        print(f"📊 Instance: {service_instance.name} ({service_instance.service_type.value})")
        
        if service_instance.service_type != ServiceType.RADARR:
            print(f"❌ MOVIE INTEGRATION FAILED: Wrong service type for movie request")
            print(f"📊 Expected: {ServiceType.RADARR.value}")
            print(f"📊 Got: {service_instance.service_type.value}")
            return None
        
        print(f"✅ Service type validation passed (RADARR)")
        
        # Create Radarr service for this specific instance
        print(f"🔧 Creating Radarr service for instance {service_instance.name}...")
        radarr_service = await self._create_radarr_service(service_instance)
        if not radarr_service:
            print(f"❌ MOVIE INTEGRATION FAILED: Could not create RadarrService")
            return None
        
        print(f"✅ RadarrService created successfully")
        print(f"📊 Service URL: {radarr_service.base_url}")
        print(f"📊 API Key Present: {'✅' if radarr_service.api_key else '❌'}")
        if radarr_service.api_key:
            print(f"📊 API Key Preview: {radarr_service.api_key[:8]}***{radarr_service.api_key[-4:] if len(radarr_service.api_key) > 12 else '***'}")
        
        # Check if integration is enabled for this instance
        print(f"🔍 Checking instance settings...")
        instance_settings = service_instance.get_settings()
        print(f"📊 Instance Settings: {instance_settings}")
        
        enable_integration = instance_settings.get('enable_integration', True)
        print(f"📊 Integration Enabled: {enable_integration}")
        
        if not enable_integration:
            print(f"❌ MOVIE INTEGRATION FAILED: Integration disabled for Radarr instance {service_instance.name}")
            return None
        
        print(f"✅ Integration enabled for instance")
        print(f"🎬 Proceeding with movie integration:")
        print(f"📊 Movie: {media_request.title}")
        print(f"📊 TMDB ID: {media_request.tmdb_id}")
        print(f"📊 Quality Tier: {media_request.requested_quality_tier}")
        print(f"📊 Instance Category: {service_instance.instance_category}")
        print(f"📊 User ID: {media_request.user_id}")
        
        try:
            print(f"🚀 Calling radarr_service.add_movie with 30s timeout...")
            print(f"📊 Method Parameters:")
            print(f"📊   - tmdb_id: {media_request.tmdb_id}")
            print(f"📊   - user_id: {media_request.user_id}")
            print(f"📊   - quality_tier: {media_request.requested_quality_tier}")
            print(f"📊   - instance_category: {service_instance.instance_category}")
            
            # Add timeout to prevent hanging
            result = await asyncio.wait_for(
                radarr_service.add_movie(
                    tmdb_id=media_request.tmdb_id,
                    user_id=media_request.user_id,
                    quality_tier=media_request.requested_quality_tier,
                    instance_category=service_instance.instance_category
                ),
                timeout=30.0
            )
            
            print(f"📡 RadarrService.add_movie returned: {result}")
            
            if result:
                success_result = {
                    'service': f'Radarr ({service_instance.name})',
                    'service_id': result.get('id'),
                    'title': result.get('title', media_request.title),
                    'instance_id': service_instance.id,
                    'quality_tier': media_request.requested_quality_tier
                }
                print(f"✅ MOVIE INTEGRATION SUCCESS: {success_result}")
                return success_result
            else:
                print(f"❌ MOVIE INTEGRATION FAILED: RadarrService.add_movie returned None")
                print(f"📊 Movie: {media_request.title}")
                print(f"📊 Instance: {service_instance.name}")
                return None
                
        except asyncio.TimeoutError:
            print(f"⏰ MOVIE INTEGRATION TIMEOUT: 30s timeout exceeded for request {media_request.id} on instance {service_instance.name}")
            return None
    
    async def _integrate_tv_request(
        self, 
        media_request: MediaRequest, 
        service_instance: ServiceInstance
    ) -> Optional[Dict[str, Any]]:
        """Integrate TV request with Sonarr instance"""
        
        if service_instance.service_type != ServiceType.SONARR:
            print(f"❌ Wrong service type for TV request: {service_instance.service_type}")
            return None
        
        # Create Sonarr service for this specific instance
        sonarr_service = await self._create_sonarr_service(service_instance)
        if not sonarr_service:
            return None
        
        # Check if integration is enabled for this instance
        instance_settings = service_instance.get_settings()
        if not instance_settings.get('enable_integration', True):
            print(f"⚠️ Integration disabled for Sonarr instance {service_instance.name}")
            return None
        
        print(f"📺 Sending TV show '{media_request.title}' (TMDB: {media_request.tmdb_id}) to Sonarr instance '{service_instance.name}'")
        print(f"🔍 Quality tier: {media_request.requested_quality_tier}")
        print(f"🔍 Instance category: {service_instance.instance_category}")
        
        # Handle season-specific and episode-specific requests
        season_number = media_request.season_number if media_request.is_season_request else None
        episode_number = media_request.episode_number if media_request.is_episode_request else None
        
        try:
            # Add timeout to prevent hanging
            result = await asyncio.wait_for(
                sonarr_service.add_tv_show(
                    tmdb_id=media_request.tmdb_id,
                    user_id=media_request.user_id,
                    season_number=season_number,
                    episode_number=episode_number,
                    quality_tier=media_request.requested_quality_tier,
                    instance_category=service_instance.instance_category
                ),
                timeout=30.0
            )
            
            if result:
                return {
                    'service': f'Sonarr ({service_instance.name})',
                    'service_id': result.get('id'),
                    'title': result.get('title', media_request.title),
                    'instance_id': service_instance.id,
                    'quality_tier': media_request.requested_quality_tier,
                    'season_number': season_number,
                    'episode_number': episode_number
                }
            else:
                print(f"❌ Failed to add TV show to Sonarr instance {service_instance.name}: {media_request.title}")
                return None
                
        except asyncio.TimeoutError:
            print(f"⏰ Sonarr integration timeout for request {media_request.id} on instance {service_instance.name}")
            return None
    
    async def _create_radarr_service(self, service_instance: ServiceInstance) -> Optional[RadarrService]:
        """Create RadarrService for specific instance"""
        print(f"\n🔧 ===== CREATING RADARR SERVICE ===== 🔧")
        print(f"📊 Instance: {service_instance.name}")
        print(f"📊 Instance URL: {service_instance.url}")
        print(f"📊 Instance API Key: {'Present' if service_instance.api_key else 'Missing'}")
        
        try:
            print(f"🔧 Initializing RadarrService with session...")
            # Initialize RadarrService with instance-specific configuration
            radarr_service = RadarrService(self.session)
            
            print(f"🔍 Getting service instance settings...")
            # Override service configuration with instance settings
            settings = service_instance.get_settings()
            print(f"📊 Instance Settings: {settings}")
            
            print(f"🔗 Building service URL...")
            # Build URL from instance configuration
            if settings.get('hostname') and settings.get('port'):
                protocol = 'https' if settings.get('use_ssl', False) else 'http'
                base_url = f"{protocol}://{settings['hostname']}:{settings['port']}"
                print(f"📊 Built URL from hostname/port: {base_url}")
                if settings.get('base_url'):
                    base_url = f"{base_url}/{settings['base_url'].strip('/')}"
                    print(f"📊 Added base_url path: {base_url}")
            else:
                base_url = service_instance.url.rstrip('/')
                print(f"📊 Using instance URL: {base_url}")
                if settings.get('base_url'):
                    base_url = f"{base_url}/{settings['base_url'].strip('/')}"
                    print(f"📊 Added base_url path: {base_url}")
            
            print(f"🔄 Overriding RadarrService properties...")
            # Override service properties
            radarr_service.base_url = base_url
            radarr_service.api_key = service_instance.api_key
            radarr_service.instance = service_instance
            
            print(f"✅ RadarrService created successfully:")
            print(f"📊 Service URL: {radarr_service.base_url}")
            print(f"📊 API Key: {'Present' if radarr_service.api_key else 'Missing'}")
            if radarr_service.api_key:
                print(f"📊 API Key Preview: {radarr_service.api_key[:8]}***{radarr_service.api_key[-4:] if len(radarr_service.api_key) > 12 else '***'}")
            print(f"📊 Instance Reference: {radarr_service.instance.name if radarr_service.instance else 'None'}")
            
            return radarr_service
            
        except Exception as e:
            print(f"❌ RADARR SERVICE CREATION FAILED: Error creating RadarrService for instance {service_instance.name}: {e}")
            import traceback
            print(f"🔍 Stack trace from RadarrService creation:")
            traceback.print_exc()
            return None
    
    async def _create_sonarr_service(self, service_instance: ServiceInstance) -> Optional[SonarrService]:
        """Create SonarrService for specific instance"""
        try:
            # Initialize SonarrService with instance-specific configuration
            sonarr_service = SonarrService(self.session)
            
            # Override service configuration with instance settings
            settings = service_instance.get_settings()
            
            # Build URL from instance configuration
            if settings.get('hostname') and settings.get('port'):
                protocol = 'https' if settings.get('use_ssl', False) else 'http'
                base_url = f"{protocol}://{settings['hostname']}:{settings['port']}"
                if settings.get('base_url'):
                    base_url = f"{base_url}/{settings['base_url'].strip('/')}"
            else:
                base_url = service_instance.url.rstrip('/')
                if settings.get('base_url'):
                    base_url = f"{base_url}/{settings['base_url'].strip('/')}"
            
            # Override service properties
            sonarr_service.base_url = base_url
            sonarr_service.api_key = service_instance.api_key
            sonarr_service.instance = service_instance
            
            return sonarr_service
            
        except Exception as e:
            print(f"❌ Error creating SonarrService for instance {service_instance.name}: {e}")
            return None
    
    async def test_instance_connection(self, service_instance: ServiceInstance) -> Dict[str, Any]:
        """Test connection to a service instance"""
        return await service_instance.test_connection()
    
    async def get_instance_quality_profiles(self, service_instance: ServiceInstance) -> list:
        """Get quality profiles from a service instance"""
        if not service_instance.is_enabled:
            return []
        
        try:
            if service_instance.service_type == ServiceType.RADARR:
                radarr_service = await self._create_radarr_service(service_instance)
                if radarr_service:
                    return await radarr_service.get_quality_profiles()
            elif service_instance.service_type == ServiceType.SONARR:
                sonarr_service = await self._create_sonarr_service(service_instance)
                if sonarr_service:
                    return await sonarr_service.get_quality_profiles()
        except Exception as e:
            print(f"❌ Error getting quality profiles from {service_instance.name}: {e}")
        
        return []
    
    async def get_4k_handling_strategy(self, service_instance: ServiceInstance) -> str:
        """
        Determine 4K handling strategy for an instance
        
        Returns:
            "dedicated": Instance is dedicated to 4K content
            "profile": Instance handles 4K via quality profiles
            "none": Instance doesn't support 4K
        """
        settings = service_instance.get_settings()
        
        # Check if this is a dedicated 4K instance
        if service_instance.is_4k_default or service_instance.instance_category == "4k":
            return "dedicated"
        
        # Check if instance has 4K quality profiles configured
        quality_profiles = await self.get_instance_quality_profiles(service_instance)
        has_4k_profiles = any(
            profile.get('name', '').lower().find('4k') != -1 or
            profile.get('name', '').lower().find('2160p') != -1
            for profile in quality_profiles
        )
        
        if has_4k_profiles:
            return "profile"
        
        return "none"


# Service factory function
async def get_multi_instance_integration_service(session: Session) -> MultiInstanceIntegrationService:
    """Get multi-instance integration service"""
    return MultiInstanceIntegrationService(session)

# Updated integration function for use in request endpoints
async def integrate_with_multi_instance_services(media_request: MediaRequest, session: Session) -> Optional[Dict]:
    """
    Updated integration function that uses multi-instance support
    """
    integration_service = MultiInstanceIntegrationService(session)
    return await integration_service.integrate_request(media_request)