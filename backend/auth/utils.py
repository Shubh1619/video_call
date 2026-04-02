from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from backend.email.db import get_db
from backend.models.user import User
from backend.core.config import SECRET_KEY
import re
import bcrypt
import uuid
import hashlib
import secrets

# -----------------------------
# Configuration
# -----------------------------
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 10
REFRESH_TOKEN_EXPIRE_DAYS = 30
MAX_PASSWORD_BYTES = 72

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Password validation rules
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

# -----------------------------
# Password utils
# -----------------------------
def truncate_password(password: str) -> str:
    return password.encode("utf-8")[:MAX_PASSWORD_BYTES].decode("utf-8", "ignore")

def get_password_hash(password: str) -> str:
    truncated = truncate_password(password)
    return bcrypt.hashpw(truncated.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    truncated = truncate_password(plain_password)
    return bcrypt.checkpw(truncated.encode("utf-8"), hashed_password.encode("utf-8"))

def is_password_too_long(password: str) -> bool:
    return len(password.encode("utf-8")) > MAX_PASSWORD_BYTES


def _as_utc(dt_obj: datetime | None) -> datetime:
    if dt_obj is None:
        return datetime.now(timezone.utc)
    if dt_obj.tzinfo is None:
        return dt_obj.replace(tzinfo=timezone.utc)
    return dt_obj.astimezone(timezone.utc)

# -----------------------------
# Password Strength Validation
# -----------------------------
def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validates password strength.
    Returns (is_valid, error_message)
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
    
    if len(password) > MAX_PASSWORD_LENGTH:
        return False, f"Password must not exceed {MAX_PASSWORD_LENGTH} characters."
    
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit."
    
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character (!@#$%^&*(),.?\":{}|<>)."
    
    common_passwords = [
        "password", "password123", "123456", "12345678", "qwerty",
        "abc123", "monkey", "1234567", "letmein", "trustno1",
        "dragon", "baseball", "iloveyou", "master", "sunshine",
        "ashley", "bailey", "shadow", "123123", "654321",
        "superman", "qazwsx", "michael", "football", "password1",
        "password123", "welcome", "welcome1", "admin", "login"
    ]
    if password.lower() in common_passwords:
        return False, "This password is too common. Please choose a stronger password."
    
    return True, ""

# -----------------------------
# JWT utils (with timezone-aware datetimes)
# -----------------------------
def create_access_token(
    data: dict,
    expires_delta: timedelta = None,
    password_updated_at: datetime | None = None,
) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({
        "exp": expire,
        "iat": int(now.timestamp()),
        "sv": int(data.get("sv", 1)),
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update(
        {
            "exp": expire,
            "iat": int(now.timestamp()),
            "scope": "refresh",
        }
    )
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_password_reset_token(
    email: str,
    jti: str,
    expires_minutes: int = PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": email,
        "jti": jti,
        "scope": "password_reset",
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_password_reset_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except ExpiredSignatureError:
        return {"error": "expired"}
    except JWTError:
        return {"error": "invalid"}

    if payload.get("scope") != "password_reset":
        return {"error": "invalid"}

    email = payload.get("sub")
    jti = payload.get("jti")
    if not email or not jti:
        return {"error": "invalid"}
    return {"email": str(email), "jti": str(jti)}


def generate_jti() -> str:
    return uuid.uuid4().hex

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_numeric_otp(length: int = 6) -> str:
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(length))

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception

    return user
