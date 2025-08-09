"""
File-based PIN store for Docker persistence
Handles Plex OAuth PIN storage across container restarts
"""

import json
import os
import time
from typing import Dict, Optional
from pathlib import Path

class PinStore:
    def __init__(self, store_path: Optional[str] = None):
        if store_path is None:
            # Use different paths for Docker vs local development
            if os.path.exists("/app") and os.access("/app", os.W_OK):
                # Docker environment
                store_path = "/app/data/pin_store.json"
            else:
                # Local development environment
                store_path = "./data/pin_store.json"
        
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache = {}
        self._last_load = 0
        self.cache_timeout = 30  # seconds
    
    def _load_store(self) -> Dict:
        """Load PIN store from file"""
        try:
            # Use cache if recent
            if time.time() - self._last_load < self.cache_timeout and self._cache:
                return self._cache
            
            if self.store_path.exists():
                with open(self.store_path, 'r') as f:
                    data = json.load(f)
                    # Clean expired PINs (older than 10 minutes)
                    current_time = time.time()
                    cleaned_data = {
                        k: v for k, v in data.items() 
                        if current_time - v.get('timestamp', 0) < 600  # 10 minutes
                    }
                    if len(cleaned_data) != len(data):
                        self._save_store(cleaned_data)
                    self._cache = cleaned_data
                    self._last_load = current_time
                    return self._cache
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load PIN store: {e}")
        
        return {}
    
    def _save_store(self, data: Dict):
        """Save PIN store to file"""
        try:
            # Atomic write
            temp_path = self.store_path.with_suffix('.tmp')
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2)
            temp_path.rename(self.store_path)
            self._cache = data
            self._last_load = time.time()
        except IOError as e:
            print(f"Error: Could not save PIN store: {e}")
    
    def __contains__(self, pin_id: int) -> bool:
        """Check if PIN ID exists"""
        store = self._load_store()
        return str(pin_id) in store
    
    def __getitem__(self, pin_id: int) -> Dict:
        """Get PIN data"""
        store = self._load_store()
        return store[str(pin_id)]
    
    def __setitem__(self, pin_id: int, value: Dict):
        """Set PIN data"""
        store = self._load_store()
        value['timestamp'] = time.time()  # Add timestamp
        store[str(pin_id)] = value
        self._save_store(store)
    
    def __delitem__(self, pin_id: int):
        """Delete PIN data"""
        store = self._load_store()
        if str(pin_id) in store:
            del store[str(pin_id)]
            self._save_store(store)
    
    def get(self, pin_id: int, default=None):
        """Get PIN data with default"""
        store = self._load_store()
        return store.get(str(pin_id), default)
    
    def cleanup_expired(self):
        """Remove expired PINs (older than 10 minutes)"""
        store = self._load_store()
        current_time = time.time()
        expired_keys = []
        
        for pin_id, data in store.items():
            if current_time - data.get('timestamp', 0) > 600:  # 10 minutes
                expired_keys.append(pin_id)
        
        if expired_keys:
            for key in expired_keys:
                del store[key]
            self._save_store(store)
            print(f"Cleaned up {len(expired_keys)} expired PINs")

# Global instance
pin_store = PinStore()