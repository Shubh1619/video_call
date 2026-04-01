from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from backend.models.user import Base


def utc_now():
    return datetime.now(timezone.utc)


class AuthAuditLog(Base):
    __tablename__ = "auth_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    event = Column(String(64), nullable=False, index=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    metadata_json = Column(String(2048), nullable=True)

    user = relationship("User", back_populates="auth_audit_logs")
