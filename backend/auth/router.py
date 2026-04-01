from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi.security import OAuth2PasswordRequestForm
import os
import logging
from datetime import datetime, timedelta, timezone
import json

from backend.email.db import get_db
from backend.auth.utils import (
    create_access_token,
    create_refresh_token,
    create_password_reset_token,
    generate_jti,
    verify_password_reset_token,
    decode_token,
    hash_token,
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
from backend.models.auth_session import AuthSession
from backend.models.auth_audit_log import AuthAuditLog
from backend.auth.schemas import (
    UserCreate,
    Token,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
    RefreshTokenRequest,
    LogoutRequest,
    SessionResponse,
    MessageResponse,
)
from backend.core.rate_limit import rate_limit_auth, limiter
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


def _extract_client_meta(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, ua


def _log_auth_event(
    db: Session,
    event: str,
    request: Request | None = None,
    user_id: int | None = None,
    metadata: dict | None = None,
):
    ip, ua = _extract_client_meta(request) if request else (None, None)
    db.add(
        AuthAuditLog(
            user_id=user_id,
            event=event,
            ip_address=ip,
            user_agent=ua,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=True),
        )
    )


def _create_session_tokens(
    db: Session,
    user: User,
    request: Request,
) -> tuple[str, str, AuthSession]:
    session_id = generate_jti()
    access_token = create_access_token(
        {"sub": user.email, "sid": session_id, "sv": int(user.session_version or 1)},
        password_updated_at=_ensure_password_updated_at(user),
    )
    refresh_token = create_refresh_token(
        {"sub": user.email, "sid": session_id, "sv": int(user.session_version or 1)}
    )
    refresh_payload = decode_token(refresh_token) or {}
    refresh_exp_ts = int(refresh_payload.get("exp", 0))
    refresh_expires_at = datetime.fromtimestamp(refresh_exp_ts, tz=timezone.utc)
    ip, ua = _extract_client_meta(request)

    session_row = AuthSession(
        user_id=user.id,
        session_id=session_id,
        refresh_token_hash=hash_token(refresh_token),
        ip_address=ip,
        user_agent=ua,
        device_name=(request.headers.get("x-device-name") or "").strip() or None,
        refresh_expires_at=refresh_expires_at,
    )
    db.add(session_row)
    return access_token, refresh_token, session_row


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
    access_token, refresh_token, _ = _create_session_tokens(db, db_user, request)
    _log_auth_event(db, "register", request, user_id=db_user.id)
    db.commit()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": 2 * 60 * 60,
        "token_type": "bearer",
    }

# -------------------------
# Login
# -------------------------
@router.post("/login", response_model=Token)
@rate_limit_auth()
@limiter.limit("10/15 minutes")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Find user by email
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        _log_auth_event(
            db,
            "login_failed",
            request,
            user_id=user.id if user else None,
            metadata={"email": form_data.username},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    access_token, refresh_token, _ = _create_session_tokens(db, user, request)
    _log_auth_event(db, "login", request, user_id=user.id)
    db.commit()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": 2 * 60 * 60,
        "token_type": "bearer",
    }


@router.post("/refresh", response_model=Token)
def refresh_access_token(
    payload: RefreshTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    token_payload = decode_token(payload.refresh_token)
    if not token_payload or token_payload.get("scope") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    email = token_payload.get("sub")
    session_id = token_payload.get("sid")
    token_sv = token_payload.get("sv")
    token_hash = hash_token(payload.refresh_token)
    if not email or not session_id or token_sv is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if int(token_sv) != int(user.session_version or 1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    session_row = (
        db.query(AuthSession)
        .filter(
            AuthSession.user_id == user.id,
            AuthSession.session_id == session_id,
            AuthSession.refresh_token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
        )
        .first()
    )
    if not session_row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    now_utc = _utc_now()
    refresh_exp = session_row.refresh_expires_at
    if refresh_exp.tzinfo is None:
        refresh_exp = refresh_exp.replace(tzinfo=timezone.utc)
    if refresh_exp < now_utc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    # Rotate refresh token.
    new_refresh_token = create_refresh_token({"sub": user.email, "sid": session_id, "sv": int(user.session_version or 1)})
    new_refresh_payload = decode_token(new_refresh_token) or {}
    new_exp = datetime.fromtimestamp(int(new_refresh_payload.get("exp", 0)), tz=timezone.utc)
    session_row.refresh_token_hash = hash_token(new_refresh_token)
    session_row.refresh_expires_at = new_exp
    session_row.last_seen_at = now_utc

    new_access_token = create_access_token(
        {"sub": user.email, "sid": session_id, "sv": int(user.session_version or 1)},
        password_updated_at=_ensure_password_updated_at(user),
    )
    _log_auth_event(db, "token_refresh", request, user_id=user.id)
    db.commit()
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "expires_in": 2 * 60 * 60,
        "token_type": "bearer",
    }


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
        _log_auth_event(db, "password_reset_requested", request, user_id=user.id)
        db.commit()

    # Always return generic success to avoid user enumeration.
    return {
        "message": "If an account with that email exists, a reset link has been sent."
    }


@router.post("/reset-password", response_model=MessageResponse)
@rate_limit_auth()
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    verified = verify_password_reset_token(payload.token)
    if not verified or verified.get("error") == "invalid":
        _log_auth_event(db, "password_reset_invalid", request, metadata={"reason": "invalid_token"})
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid reset token")
    if verified.get("error") == "expired":
        _log_auth_event(db, "password_reset_expired", request, metadata={"reason": "jwt_expired"})
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Reset link has expired")
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid reset token")

    token_row = db.query(PasswordResetToken).filter(
        PasswordResetToken.jti == jti,
        PasswordResetToken.user_id == user.id,
    ).first()

    if not token_row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid reset token")
    if token_row.used_at is not None:
        _log_auth_event(db, "password_reset_reused", request, user_id=user.id, metadata={"jti": jti})
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This reset link has already been used")

    now_utc = _utc_now()
    expires_at = token_row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now_utc:
        _log_auth_event(db, "password_reset_expired", request, user_id=user.id, metadata={"jti": jti})
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Reset link has expired")

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

    _log_auth_event(db, "password_reset_success", request, user_id=user.id)
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
    now_utc = _utc_now()
    current_user.password_updated_at = now_utc
    _log_auth_event(db, "password_changed", request, user_id=current_user.id)
    db.commit()

    return {"message": "Password changed successfully"}


@router.get("/sessions")
def list_active_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessions = (
        db.query(AuthSession)
        .filter(
            AuthSession.user_id == current_user.id,
            AuthSession.revoked_at.is_(None),
        )
        .order_by(AuthSession.created_at.desc())
        .all()
    )
    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
                "device_name": s.device_name,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "last_seen_at": s.last_seen_at.isoformat() if s.last_seen_at else None,
                "refresh_expires_at": s.refresh_expires_at.isoformat() if s.refresh_expires_at else None,
            }
            for s in sessions
        ]
    }


@router.post("/logout-all", response_model=MessageResponse)
def logout_all_sessions(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now_utc = _utc_now()
    current_user.session_version = int(current_user.session_version or 1) + 1
    db.query(AuthSession).filter(
        AuthSession.user_id == current_user.id,
        AuthSession.revoked_at.is_(None),
    ).update({"revoked_at": now_utc, "last_seen_at": now_utc}, synchronize_session=False)
    _log_auth_event(db, "logout_all", request, user_id=current_user.id)
    db.commit()
    return {"message": "Logged out from all devices successfully"}


@router.post("/logout", response_model=MessageResponse)
def logout_current_session(
    payload: LogoutRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    token_payload = decode_token(payload.refresh_token)
    if not token_payload or token_payload.get("scope") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    session_id = token_payload.get("sid")
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    token_hash = hash_token(payload.refresh_token)
    session_row = (
        db.query(AuthSession)
        .filter(
            AuthSession.user_id == current_user.id,
            AuthSession.session_id == session_id,
            AuthSession.refresh_token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
        )
        .first()
    )
    if session_row:
        now_utc = _utc_now()
        session_row.revoked_at = now_utc
        session_row.last_seen_at = now_utc

    _log_auth_event(db, "logout", request, user_id=current_user.id, metadata={"session_id": session_id})
    db.commit()
    return {"message": "Logged out successfully"}
