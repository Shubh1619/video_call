from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from backend.models.user import Base


def utc_now():
    return datetime.now(timezone.utc)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(64), nullable=False, unique=True, index=True)
    refresh_token_hash = Column(String(128), nullable=False, unique=True, index=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    device_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    last_seen_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    refresh_expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)

    user = relationship("User", back_populates="auth_sessions")
