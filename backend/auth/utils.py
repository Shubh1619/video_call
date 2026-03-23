from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from backend.email.db import get_db
from backend.models.user import User
from backend.core.config import SECRET_KEY
import re
import bcrypt

# -----------------------------
# Configuration
# -----------------------------
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
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
def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

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
