#!/usr/bin/env python3
"""
Test webhook payload processing
"""

def test_webhook_logic():
    """Test the webhook event processing logic"""
    
    # Test Radarr event processing
    from app.api.webhooks import determine_status_from_radarr_event
    from app.models.media_request import RequestStatus
    
    print("🧪 Testing Radarr webhook logic...")
    
    # Test Grab event
    status = determine_status_from_radarr_event("Grab", {}, RequestStatus.APPROVED)
    print(f"Grab event: APPROVED → {status.value}")
    assert status == RequestStatus.DOWNLOADING
    
    # Test Download event  
    status = determine_status_from_radarr_event("Download", {}, RequestStatus.DOWNLOADING)
    print(f"Download event: DOWNLOADING → {status.value}")
    assert status == RequestStatus.DOWNLOADED
    
    print("✅ Radarr webhook logic tests passed!")
    
    # Test Sonarr event processing
    from app.api.webhooks import determine_status_from_sonarr_event
    
    print("\n🧪 Testing Sonarr webhook logic...")
    
    # Test Grab event
    status = determine_status_from_sonarr_event("Grab", {}, RequestStatus.APPROVED)
    print(f"Grab event: APPROVED → {status.value}")
    assert status == RequestStatus.DOWNLOADING
    
    # Test Download event
    status = determine_status_from_sonarr_event("Download", {}, RequestStatus.DOWNLOADING)
    print(f"Download event: DOWNLOADING → {status.value}")
    assert status == RequestStatus.DOWNLOADED
    
    print("✅ Sonarr webhook logic tests passed!")

def test_sample_payloads():
    """Test with sample webhook payloads"""
    
    print("\n🧪 Testing sample webhook payloads...")
    
    # Sample Radarr Download payload
    radarr_payload = {
        "eventType": "Download",
        "movie": {
            "id": 123,
            "tmdbId": 456,
            "title": "Test Movie"
        },
        "movieFile": {
            "id": 789,
            "path": "/movies/Test Movie (2023).mkv"
        }
    }
    
    print(f"Sample Radarr payload: {radarr_payload}")
    
    # Sample Sonarr Download payload
    sonarr_payload = {
        "eventType": "Download", 
        "series": {
            "id": 123,
            "tmdbId": 456,
            "title": "Test Series"
        },
        "episodes": [{"id": 1, "title": "Episode 1"}],
        "episodeFile": {
            "id": 789,
            "path": "/tv/Test Series/Season 1/Test Series S01E01.mkv"
        }
    }
    
    print(f"Sample Sonarr payload: {sonarr_payload}")
    print("✅ Sample payloads ready for testing!")

if __name__ == "__main__":
    test_webhook_logic()
    test_sample_payloads()
    print("\n🎉 All webhook tests completed successfully!")