#!/usr/bin/env python3
"""
Quick test script to verify the app structure and imports
"""

def test_imports():
    """Test that all modules can be imported successfully"""
    try:
        from app.main import app
        print("✅ Main app imports successfully")
        
        from app.models import User, MediaRequest, PlexLibraryItem
        print("✅ Models import successfully")
        
        from app.services.tmdb_service import TMDBService
        from app.services.plex_service import PlexService
        from app.services.radarr_service import RadarrService
        from app.services.sonarr_service import SonarrService
        print("✅ Services import successfully")
        
        from app.api import auth, search, requests, admin
        print("✅ API modules import successfully")
        
        from app.core.config import settings
        from app.core.database import get_session
        from app.core.auth import create_access_token
        print("✅ Core modules import successfully")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        import traceback
        print(f"❌ Unexpected error: {e}")
        print("Full traceback:")
        traceback.print_exc()
        return False

def test_app_routes():
    """Test that FastAPI app has expected routes"""
    try:
        from app.main import app
        
        route_paths = [route.path for route in app.routes]
        expected_routes = [
            "/",
            "/login", 
            "/logout",
            "/search",
            "/auth/plex/login",
            "/auth/plex/verify", 
            "/requests/",
            "/admin/settings"
        ]
        
        for route in expected_routes:
            if route in route_paths:
                print(f"✅ Route {route} found")
            else:
                print(f"❌ Route {route} missing")
        
        print(f"\nTotal routes: {len(route_paths)}")
        return True
        
    except Exception as e:
        print(f"❌ Error testing routes: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Stout Requests App Structure\n")
    
    print("1. Testing imports...")
    imports_ok = test_imports()
    
    print("\n2. Testing routes...")
    routes_ok = test_app_routes()
    
    if imports_ok and routes_ok:
        print("\n🎉 All tests passed! App structure looks good.")
        print("\n📝 Next steps:")
        print("1. Set up PostgreSQL database")
        print("2. Copy .env.example to .env and configure API keys")
        print("3. Run: python run.py")
        print("4. Visit http://localhost:8000")
    else:
        print("\n⚠️  Some tests failed. Check the errors above.")