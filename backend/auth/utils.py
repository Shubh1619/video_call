from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from backend.core.db import get_db
from backend.models.user import User

# -----------------------------
# Configuration
# -----------------------------
SECRET_KEY = "your-secret-key"  # Change this to a secure key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
MAX_PASSWORD_BYTES = 72

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# -----------------------------
# Password utils
# -----------------------------
def truncate_password(password: str) -> str:
    return password.encode("utf-8")[:MAX_PASSWORD_BYTES].decode("utf-8", "ignore")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(truncate_password(password))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(truncate_password(plain_password), hashed_password)

def is_password_too_long(password: str) -> bool:
    return len(password.encode("utf-8")) > MAX_PASSWORD_BYTES

# -----------------------------
# JWT utils
# -----------------------------
def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

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
