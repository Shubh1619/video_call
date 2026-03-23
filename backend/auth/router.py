from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from backend.email.db import get_db
from backend.auth.utils import (
    create_access_token,
    get_password_hash,
    verify_password,
    is_password_too_long,
    validate_password_strength,
    MAX_PASSWORD_BYTES,
    get_current_user
)
from backend.models.user import User
from backend.auth.schemas import UserCreate, Token
from backend.core.rate_limit import rate_limit_auth

router = APIRouter()

# -------------------------
# Register
# -------------------------
@router.post("/register", response_model=Token)
@rate_limit_auth()
def register(user: UserCreate, request: Request, db: Session = Depends(get_db)):
    # Validate password strength
    is_valid, error_message = validate_password_strength(user.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message
        )

    # Check if user exists
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Check password length (bcrypt limit)
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
@rate_limit_auth()
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
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


@router.get("/user")
def get_logged_in_user(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email
    }