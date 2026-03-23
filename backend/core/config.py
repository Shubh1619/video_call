import os
from dotenv import load_dotenv
import secrets


load_dotenv()

# -----------------------------
# DOMAIN CONFIGURATION
# -----------------------------
MY_DOMAIN = os.getenv("MY_DOMAIN", "https://meet-frontend-4op.pages.dev")

# -----------------------------
# DATABASE CONFIGURATION
# -----------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

# -----------------------------
# EMAIL CONFIGURATION
# -----------------------------
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM")
MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
MAIL_SERVER = os.getenv("MAIL_SERVER")
MAIL_STARTTLS = os.getenv("MAIL_STARTTLS", "True").lower() == "true"
MAIL_SSL_TLS = os.getenv("MAIL_SSL_TLS", "False").lower() == "true"
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "AI Meeting Assistant")
USE_CREDENTIALS = os.getenv("USE_CREDENTIALS", "True").lower() == "true"

MAIL_CONFIG = {
    "MAIL_USERNAME": MAIL_USERNAME,
    "MAIL_PASSWORD": MAIL_PASSWORD,
    "MAIL_FROM": MAIL_FROM,
    "MAIL_PORT": MAIL_PORT,
    "MAIL_SERVER": MAIL_SERVER,
    "MAIL_STARTTLS": MAIL_STARTTLS,
    "MAIL_SSL_TLS": MAIL_SSL_TLS,
    "MAIL_FROM_NAME": MAIL_FROM_NAME,
    "USE_CREDENTIALS": USE_CREDENTIALS,
}

# -----------------------------
# SECRET KEY VALIDATION (CRITICAL)
# -----------------------------
SECRET_KEY = os.getenv("SECRET_KEY")

# Placeholder values that should NEVER be used in production
FORBIDDEN_KEYS = {
    "your-secret-key",
    "your-secret-key-here",
    "secret",
    "changeme",
    "dev-secret-key",
    "test-secret-key",
    "secret-key",
    "default-secret",
}

if not SECRET_KEY:
    print("=" * 60)
    print("CRITICAL ERROR: SECRET_KEY not set in environment!")
    print("=" * 60)
    raise ValueError(
        "SECRET_KEY environment variable is required. "
        "Please set it before starting the application."
    )

if len(SECRET_KEY) < 32:
    raise ValueError(
        f"SECRET_KEY must be at least 32 characters long. "
        f"Current length: {len(SECRET_KEY)}. "
        f"Please set a stronger SECRET_KEY in your environment."
    )

if SECRET_KEY.lower() in FORBIDDEN_KEYS or any(
    SECRET_KEY.startswith(k) for k in ["your-", "dev-", "test-"]
):
    raise ValueError(
        f"SECRET_KEY appears to be a placeholder value ('{SECRET_KEY[:20]}...'). "
        f"Please set a secure, unique SECRET_KEY in your environment. "
        f"Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
    )

# Validate it's not the old hardcoded fallback
if SECRET_KEY == "your-secret-key" * 2 or SECRET_KEY == "changeme" * 4:
    raise ValueError("SECRET_KEY is using a prohibited value.")

# -----------------------------
# JWT SECRET FOR STT (must match SECRET_KEY)
# -----------------------------
JWT_SECRET = os.getenv("JWT_SECRET")

if not JWT_SECRET:
    # Default to SECRET_KEY for backward compatibility
    JWT_SECRET = SECRET_KEY
    print("⚠️ WARNING: JWT_SECRET not set. Using SECRET_KEY as JWT_SECRET.")
else:
    if JWT_SECRET in FORBIDDEN_KEYS:
        raise ValueError(
            "JWT_SECRET appears to be a placeholder. "
            "Please set a secure JWT_SECRET or leave it unset to use SECRET_KEY."
        )

# -----------------------------
# CORS CONFIGURATION
# -----------------------------
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000,http://127.0.0.1:8080"
).split(",")

# -----------------------------
# REDIS CONFIGURATION (for distributed sessions/rate limiting)
# -----------------------------
REDIS_URL = os.getenv("REDIS_URL")
REDIS_ENABLED = REDIS_URL is not None

if REDIS_ENABLED:
    print(f"✓ Redis enabled: {REDIS_URL.split('@')[1] if '@' in REDIS_URL else REDIS_URL}")
else:
    print("ℹ️ Redis not configured. Rate limiting will use in-memory storage (single instance only).")

# -----------------------------
# RATE LIMITING CONFIG
# -----------------------------
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
RATE_LIMIT_AUTH_PER_MINUTE = int(os.getenv("RATE_LIMIT_AUTH_PER_MINUTE", "10"))
RATE_LIMIT_STRICT_PER_MINUTE = int(os.getenv("RATE_LIMIT_STRICT_PER_MINUTE", "5"))

# -----------------------------
# TIMEZONE CONFIG
# -----------------------------
TIMEZONE = os.getenv("TIMEZONE", "UTC")

print(f"✓ Configuration loaded successfully")
print(f"✓ CORS enabled for origins: {CORS_ORIGINS}")
print(f"✓ Rate limiting: {RATE_LIMIT_AUTH_PER_MINUTE} auth requests/min, {RATE_LIMIT_PER_MINUTE} general requests/min")
