from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request
from backend.core.config import REDIS_URL, REDIS_ENABLED, RATE_LIMIT_PER_MINUTE, RATE_LIMIT_AUTH_PER_MINUTE, RATE_LIMIT_STRICT_PER_MINUTE

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=REDIS_URL if REDIS_ENABLED else "memory://",
    default_limits=[f"{RATE_LIMIT_PER_MINUTE}/minute"],
)

def rate_limit_auth():
    """Rate limit for auth endpoints."""
    return limiter.limit(f"{RATE_LIMIT_AUTH_PER_MINUTE}/minute")

def rate_limit_strict():
    """Strict rate limit for sensitive operations."""
    return limiter.limit(f"{RATE_LIMIT_STRICT_PER_MINUTE}/minute")

def rate_limit_default():
    """Default rate limit."""
    return limiter.limit(f"{RATE_LIMIT_PER_MINUTE}/minute")
