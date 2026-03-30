from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from backend.models.user import Base


class Participant(Base):
    __tablename__ = "participants"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    email = Column(String(255), nullable=False, index=True)
    role = Column(String(20), nullable=False, default="participant")  # host|participant|guest
    status = Column(String(20), nullable=False, default="invited")  # invited|joined|left
    joined_at = Column(DateTime(timezone=True), nullable=True)
    left_at = Column(DateTime(timezone=True), nullable=True)

    meeting = relationship("Meeting", back_populates="participants")
    user = relationship("User", back_populates="participants")

    __table_args__ = (
        UniqueConstraint("meeting_id", "email", name="uq_participant_meeting_email"),
        Index("ix_participants_meeting_status", "meeting_id", "status"),
    )

