from datetime import datetime, timezone

from sqlalchemy import Column, Integer, Date, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import relationship

from backend.models.user import Base


def utc_now():
    return datetime.now(timezone.utc)


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    note_date = Column(Date, nullable=True)  # legacy date-wise notes compatibility
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    meeting = relationship("Meeting", back_populates="notes")
    user = relationship("User", back_populates="notes")


Index("ix_notes_meeting_created", Note.meeting_id, Note.created_at)
