"""
Redis Session Management Service

Provides distributed session storage using Redis.
Used for:
- Rate limiting with distributed counters
- Session token blacklist/revocation
- User session management
"""
import redis
import json
from typing import Optional, List
from datetime import timedelta
from backend.core.config import REDIS_URL, REDIS_ENABLED

class RedisSessionService:
    """
    Redis-based session management service.
    Falls back to no-op operations when Redis is not configured.
    """
    
    def __init__(self):
        self.enabled = REDIS_ENABLED
        self._client = None
        
        if self.enabled:
            try:
                self._client = redis.from_url(
                    REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                self._client.ping()
                print("✓ Redis connection established")
            except redis.ConnectionError as e:
                print(f"⚠️ Redis connection failed: {e}. Running without Redis.")
                self.enabled = False
                self._client = None
    
    @property
    def client(self) -> Optional[redis.Redis]:
        return self._client
    
    # -----------------------------
    # Token Blacklist / Revocation
    # -----------------------------
    
    def blacklist_token(self, jti: str, expires_in: int = 3600):
        """
        Add a token's JTI to the blacklist.
        Called during logout.
        """
        if not self.enabled or not self._client:
            return False
        
        try:
            key = f"blacklist:token:{jti}"
            self._client.setex(key, expires_in, "1")
            return True
        except redis.RedisError as e:
            print(f"Redis error blacklisting token: {e}")
            return False
    
    def is_token_blacklisted(self, jti: str) -> bool:
        """
        Check if a token's JTI is blacklisted.
        """
        if not self.enabled or not self._client:
            return False
        
        try:
            key = f"blacklist:token:{jti}"
            return self._client.exists(key) > 0
        except redis.RedisError as e:
            print(f"Redis error checking token: {e}")
            return False
    
    # -----------------------------
    # User Session Management
    # -----------------------------
    
    def set_user_session(self, user_id: int, session_data: dict, ttl: int = 86400):
        """
        Store user session data in Redis.
        Default TTL: 24 hours.
        """
        if not self.enabled or not self._client:
            return False
        
        try:
            key = f"session:user:{user_id}"
            self._client.setex(key, ttl, json.dumps(session_data))
            return True
        except redis.RedisError as e:
            print(f"Redis error setting session: {e}")
            return False
    
    def get_user_session(self, user_id: int) -> Optional[dict]:
        """
        Get user session data from Redis.
        """
        if not self.enabled or not self._client:
            return None
        
        try:
            key = f"session:user:{user_id}"
            data = self._client.get(key)
            if data:
                return json.loads(data)
            return None
        except redis.RedisError as e:
            print(f"Redis error getting session: {e}")
            return None
    
    def delete_user_session(self, user_id: int) -> bool:
        """
        Delete user session from Redis.
        Called during logout.
        """
        if not self.enabled or not self._client:
            return False
        
        try:
            key = f"session:user:{user_id}"
            self._client.delete(key)
            return True
        except redis.RedisError as e:
            print(f"Redis error deleting session: {e}")
            return False
    
    # -----------------------------
    # Rate Limiting Support
    # -----------------------------
    
    def increment_rate_limit(self, key: str, window: int = 60) -> int:
        """
        Increment a rate limit counter.
        Returns current count.
        """
        if not self.enabled or not self._client:
            return 0
        
        try:
            full_key = f"ratelimit:{key}"
            pipe = self._client.pipeline()
            pipe.incr(full_key)
            pipe.expire(full_key, window)
            results = pipe.execute()
            return results[0]
        except redis.RedisError as e:
            print(f"Redis error incrementing rate limit: {e}")
            return 0
    
    def get_rate_limit_count(self, key: str) -> int:
        """
        Get current rate limit count.
        """
        if not self.enabled or not self._client:
            return 0
        
        try:
            full_key = f"ratelimit:{key}"
            count = self._client.get(full_key)
            return int(count) if count else 0
        except redis.RedisError as e:
            print(f"Redis error getting rate limit: {e}")
            return 0
    
    # -----------------------------
    # Health Check
    # -----------------------------
    
    def health_check(self) -> dict:
        """
        Check Redis health status.
        """
        if not self.enabled:
            return {"status": "disabled", "message": "Redis not configured"}
        
        try:
            self._client.ping()
            info = self._client.info("server")
            return {
                "status": "healthy",
                "redis_version": info.get("redis_version", "unknown"),
                "uptime_seconds": info.get("uptime_in_seconds", 0)
            }
        except redis.RedisError as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Global singleton instance
redis_session = RedisSessionService()
