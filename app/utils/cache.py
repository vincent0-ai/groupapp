import redis
from flask import current_app
from typing import Any, Optional
import json

class RedisCache:
    """Redis cache client for session and data caching"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisCache, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        try:
            self.redis_client = redis.from_url(current_app.config['REDIS_URL'])
            self.redis_client.ping()
            self._initialized = True
        except Exception as e:
            print(f"Redis connection error: {e}")
            self._initialized = False
    
    def set(self, key: str, value: Any, ex: int = None) -> bool:
        """Set a value in cache"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            self.redis_client.set(key, value, ex=ex)
            return True
        except Exception as e:
            print(f"Error setting cache: {e}")
            return False
    
    def get(self, key: str) -> Optional[str]:
        """Get a value from cache"""
        try:
            value = self.redis_client.get(key)
            return value.decode('utf-8') if value else None
        except Exception as e:
            print(f"Error getting cache: {e}")
            return None
    
    def get_json(self, key: str) -> Optional[dict]:
        """Get a JSON value from cache"""
        try:
            value = self.get(key)
            return json.loads(value) if value else None
        except Exception as e:
            print(f"Error getting JSON cache: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Delete a key from cache"""
        try:
            self.redis_client.delete(key)
            return True
        except Exception as e:
            print(f"Error deleting cache: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if a key exists"""
        try:
            return self.redis_client.exists(key) > 0
        except Exception as e:
            print(f"Error checking cache existence: {e}")
            return False
    
    def increment(self, key: str, amount: int = 1) -> int:
        """Increment a counter"""
        try:
            return self.redis_client.incr(key, amount)
        except Exception as e:
            print(f"Error incrementing cache: {e}")
            return 0
    
    def expire(self, key: str, ex: int) -> bool:
        """Set expiration on a key"""
        try:
            self.redis_client.expire(key, ex)
            return True
        except Exception as e:
            print(f"Error setting expiration: {e}")
            return False
