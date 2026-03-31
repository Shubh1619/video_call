from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi.security import OAuth2PasswordRequestForm
import os
import logging
from datetime import datetime, timedelta, timezone

from backend.email.db import get_db
from backend.auth.utils import (
    create_access_token,
    create_password_reset_token,
    generate_jti,
    verify_password_reset_token,
    get_password_hash,
    verify_password,
    is_password_too_long,
    validate_password_strength,
    MAX_PASSWORD_BYTES,
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
    get_current_user,
)
from backend.models.user import User
from backend.models.password_reset_token import PasswordResetToken
from backend.auth.schemas import (
    UserCreate,
    Token,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
    MessageResponse,
)
from backend.core.rate_limit import rate_limit_auth
from backend.core.config import MY_DOMAIN
from backend.email.utils import send_password_reset_email

router = APIRouter()
logger = logging.getLogger(__name__)

# Per-email forgot-password throttle: max 5 requests / 15 minutes.
_FORGOT_PWD_WINDOW = timedelta(minutes=15)
_FORGOT_PWD_LIMIT = 5


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_password_updated_at(user: User) -> datetime:
    if getattr(user, "password_updated_at", None) is not None:
        return user.password_updated_at
    if getattr(user, "created_at", None) is not None:
        return user.created_at
    return _utc_now()


def _check_forgot_password_email_rate_limit(db: Session, email: str):
    key = (email or "").strip().lower()
    window_start = _utc_now() - _FORGOT_PWD_WINDOW

    recent_count = (
        db.query(PasswordResetToken.id)
        .join(User, User.id == PasswordResetToken.user_id)
        .filter(
            func.lower(User.email) == key,
            PasswordResetToken.created_at >= window_start,
        )
        .count()
    )

    if recent_count >= _FORGOT_PWD_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Too many reset requests for this email. Please try again later.",
        )

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
    token = create_access_token({"sub": db_user.email}, password_updated_at=_ensure_password_updated_at(db_user))
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
    token = create_access_token({"sub": user.email}, password_updated_at=_ensure_password_updated_at(user))
    return {"access_token": token, "token_type": "bearer"}


@router.get("/user")
def get_logged_in_user(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email
    }


@router.post("/forgot-password", response_model=MessageResponse)
@rate_limit_auth()
async def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    normalized_email = payload.email.strip().lower()
    _check_forgot_password_email_rate_limit(db, normalized_email)
    user = db.query(User).filter(func.lower(User.email) == normalized_email).first()

    if user:
        jti = generate_jti()
        expires_at = _utc_now() + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
        reset_token = create_password_reset_token(user.email, jti=jti)
        reset_base_url = os.getenv("RESET_PASSWORD_URL_BASE") or f"{MY_DOMAIN}/#/reset-password"
        reset_link = f"{reset_base_url}?token={reset_token}"
        app_reset_base_url = (os.getenv("APP_RESET_PASSWORD_URL_BASE") or "").strip()
        app_reset_link = f"{app_reset_base_url}?token={reset_token}" if app_reset_base_url else None

        db.add(
            PasswordResetToken(
                user_id=user.id,
                jti=jti,
                expires_at=expires_at,
                requested_ip=(request.client.host if request.client else None),
            )
        )
        db.commit()

        try:
            await send_password_reset_email(
                recipient_email=user.email,
                recipient_name=user.name,
                reset_link=reset_link,
                app_reset_link=app_reset_link,
                expires_minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
            )
        except Exception as exc:
            logger.warning("Password reset email dispatch failed: %s", exc)

    # Always return generic success to avoid user enumeration.
    return {
        "message": "If an account with that email exists, a reset link has been sent."
    }


@router.post("/reset-password", response_model=MessageResponse)
@rate_limit_auth()
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    verified = verify_password_reset_token(payload.token)
    if not verified:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    email = verified["email"]
    jti = verified["jti"]

    is_valid, error_message = validate_password_strength(payload.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_message)

    if is_password_too_long(payload.new_password):
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at most {MAX_PASSWORD_BYTES} bytes when encoded in UTF-8."
        )

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid reset token")

    token_row = db.query(PasswordResetToken).filter(
        PasswordResetToken.jti == jti,
        PasswordResetToken.user_id == user.id,
    ).first()

    if not token_row:
        raise HTTPException(status_code=400, detail="Invalid reset token")
    if token_row.used_at is not None:
        raise HTTPException(status_code=400, detail="This reset link has already been used")

    now_utc = _utc_now()
    expires_at = token_row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now_utc:
        raise HTTPException(status_code=400, detail="Reset link has expired")

    if verify_password(payload.new_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="New password must be different from the old password")

    user.hashed_password = get_password_hash(payload.new_password)
    user.password_updated_at = now_utc
    token_row.used_at = now_utc

    # Invalidate all outstanding reset links for this user.
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.jti != jti,
    ).update({"used_at": now_utc}, synchronize_session=False)

    db.commit()

    return {"message": "Password has been reset successfully"}


@router.post("/change-password", response_model=MessageResponse)
@rate_limit_auth()
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    is_valid, error_message = validate_password_strength(payload.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_message)

    if is_password_too_long(payload.new_password):
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at most {MAX_PASSWORD_BYTES} bytes when encoded in UTF-8."
        )

    if verify_password(payload.new_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="New password must be different from the old password")

    current_user.hashed_password = get_password_hash(payload.new_password)
    current_user.password_updated_at = _utc_now()
    db.commit()

    return {"message": "Password changed successfully"}
