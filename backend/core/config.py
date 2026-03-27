import os
from dotenv import load_dotenv

load_dotenv()

# -----------------------------
# RAW ENV HELPERS
# -----------------------------
_cors_origins_raw = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000,http://127.0.0.1:8080",
)

# -----------------------------
# DOMAIN CONFIGURATION
# -----------------------------
DEFAULT_HOSTED_FRONTEND = "https://meet-frontend-4op.pages.dev"
MY_DOMAIN = (os.getenv("MY_DOMAIN") or "").strip().rstrip("/")

fallback_candidates = [
    (os.getenv("PUBLIC_FRONTEND_URL") or "").strip().rstrip("/"),
    (os.getenv("FRONTEND_URL") or "").strip().rstrip("/"),
]
fallback_candidates += [
    origin.strip().rstrip("/")
    for origin in _cors_origins_raw.split(",")
    if origin.strip().startswith("https://")
    and "localhost" not in origin
    and "127.0.0.1" not in origin
]
fallback_candidates.append(DEFAULT_HOSTED_FRONTEND)
fallback_candidates = [c for c in fallback_candidates if c]

if not MY_DOMAIN:
    MY_DOMAIN = fallback_candidates[0]
    print(f"MY_DOMAIN not set. Using fallback: {MY_DOMAIN}")
elif os.getenv("RENDER") and ("localhost" in MY_DOMAIN or "127.0.0.1" in MY_DOMAIN):
    MY_DOMAIN = fallback_candidates[0]
    print(f"MY_DOMAIN was localhost on Render. Using hosted fallback: {MY_DOMAIN}")

# -----------------------------
# DATABASE CONFIGURATION
# -----------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

# -----------------------------
# EMAIL CONFIGURATION
# -----------------------------
MAIL_CONFIG = {
    "MAIL_USERNAME": os.getenv("MAIL_USERNAME"),
    "MAIL_PASSWORD": os.getenv("MAIL_PASSWORD"),
    "MAIL_FROM": os.getenv("MAIL_FROM"),
    "MAIL_PORT": int(os.getenv("MAIL_PORT", 587)),
    "MAIL_SERVER": os.getenv("MAIL_SERVER"),
    "MAIL_STARTTLS": os.getenv("MAIL_STARTTLS", "True").lower() == "true",
    "MAIL_SSL_TLS": os.getenv("MAIL_SSL_TLS", "False").lower() == "true",
    "MAIL_FROM_NAME": os.getenv("MAIL_FROM_NAME", "Meeting"),
    "USE_CREDENTIALS": os.getenv("USE_CREDENTIALS", "True").lower() == "true",
    "BREVO_API_KEY": os.getenv("BREVO_API_KEY"),
}

# -----------------------------
# REDIS CONFIGURATION (REQUIRED)
# -----------------------------
REDIS_URL = os.getenv("REDIS_URL")
REDIS_ENABLED = REDIS_URL is not None

# -----------------------------
# RATE LIMIT CONFIGURATION
# -----------------------------
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
RATE_LIMIT_AUTH_PER_MINUTE = int(os.getenv("RATE_LIMIT_AUTH_PER_MINUTE", "10"))
RATE_LIMIT_STRICT_PER_MINUTE = int(os.getenv("RATE_LIMIT_STRICT_PER_MINUTE", "5"))

# -----------------------------
# CORS CONFIGURATION (REQUIRED)
# -----------------------------
CORS_ORIGINS = os.getenv("CORS_ORIGINS", _cors_origins_raw).split(",")

# -----------------------------
# SECRET KEY (STRICT SECURITY)
# -----------------------------
SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise ValueError("SECRET_KEY not set")

if len(SECRET_KEY) < 32:
    raise ValueError("SECRET_KEY must be at least 32 characters")

# -----------------------------
# JWT SECRET
# -----------------------------
JWT_SECRET = os.getenv("JWT_SECRET", SECRET_KEY)

# -----------------------------
# DEBUG PRINTS (HELPFUL)
# -----------------------------
print("Config loaded successfully")
print(f"DOMAIN: {MY_DOMAIN}")
print(f"MAIL: {MAIL_CONFIG['MAIL_USERNAME']}")
print(f"REDIS ENABLED: {REDIS_ENABLED}")
print(f"CORS: {CORS_ORIGINS}")
