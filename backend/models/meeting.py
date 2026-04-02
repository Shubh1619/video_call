from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from backend.models.user import Base


def utc_now():
    return datetime.now(timezone.utc)


class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    agenda = Column(String(1000), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)

    room_id = Column(String(255), nullable=False, unique=True, index=True)
    meeting_link = Column(String(255), nullable=False, unique=True)
    meeting_url = Column(String(255), unique=True, index=True)

    # Preserve existing values while supporting new normalized values.
    # Accepted: instant|scheduled|regular (legacy regular is treated as scheduled in serializers).
    meeting_type = Column(String(20), default="scheduled", nullable=False)
    scheduled_start = Column(DateTime(timezone=True), nullable=False, index=True)
    scheduled_end = Column(DateTime(timezone=True), nullable=False)
    meeting_timezone = Column(String(64), nullable=False, default="UTC")

    password = Column(String(255), nullable=True)
    allow_guest = Column(Boolean, default=True, nullable=False)
    waiting_room = Column(Boolean, default=True, nullable=False)
    mute_on_join = Column(Boolean, default=False, nullable=False)
    allow_user_ai = Column(Boolean, default=False, nullable=False)
    allow_user_captions = Column(Boolean, default=False, nullable=False)
    allow_guest_screen_share = Column(Boolean, default=False, nullable=False)
    allow_user_screen_share = Column(Boolean, default=False, nullable=False)

    status = Column(String(20), default="scheduled", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_updated = Column(DateTime(timezone=True), onupdate=utc_now)

    owner = relationship("User", back_populates="owned_meetings")
    participants = relationship("Participant", back_populates="meeting", cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="meeting", cascade="all, delete-orphan")


Index("ix_meetings_owner_start", Meeting.owner_id, Meeting.scheduled_start)
