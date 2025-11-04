from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from backend.email.db import get_db
from backend.auth.utils import (
    create_access_token,
    get_password_hash,
    verify_password,
    is_password_too_long,
    MAX_PASSWORD_BYTES
)
from backend.models.user import User
from backend.auth.schemas import UserCreate, Token

router = APIRouter()

# -------------------------
# Register
# -------------------------
@router.post("/register", response_model=Token)
def register(user: UserCreate, db: Session = Depends(get_db)):
    # Check if user exists
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Check password length
    if is_password_too_long(user.password):
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at most {MAX_PASSWORD_BYTES} bytes when encoded in UTF-8."
        )

    # Hash password and save user
    hashed_password = get_password_hash(user.password)
    db_user = User(email=user.email, hashed_password=hashed_password, name=user.name)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # Create access token
    token = create_access_token({"sub": db_user.email})
    return {"access_token": token, "token_type": "bearer"}

# -------------------------
# Login
# -------------------------
@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Find user by email
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    # Create access token
    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}
