from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
import datetime
from backend.models.user import Base, User
from sqlalchemy.dialects.postgresql import ARRAY


class Meeting(Base):
    __tablename__ = "meetings"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    agenda = Column(String(255), nullable=True)
    scheduled_start = Column(DateTime, nullable=False)
    scheduled_end = Column(DateTime, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="meetings")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_updated = Column(DateTime, onupdate=datetime.datetime.utcnow)
    meeting_link = Column(String(255), nullable=False, unique=True)
    meeting_url = Column(String(255), unique=True, index=True)
    room_id = Column(String(255), nullable=False, unique=True, index=True)
    status = Column(String(50), default="scheduled", nullable=False)
    meeting_type = Column(String(50), default="regular", nullable=False)
    attendee_emails = Column(ARRAY(String), nullable=True)

    # Relationships (one-to-one)
    settings = relationship("MeetingSettings", back_populates="meeting", uselist=False)
    security = relationship("MeetingSecurity", back_populates="meeting", uselist=False)
    recording = relationship("MeetingRecording", back_populates="meeting", uselist=False)
    transcript = relationship("MeetingTranscript", back_populates="meeting", uselist=False)


class MeetingSettings(Base):
    __tablename__ = "meeting_settings"
    id = Column(Integer, primary_key=True)
    max_participants = Column(Integer, default=100)
    chat_enabled = Column(Boolean, default=True)
    screen_share_enabled = Column(Boolean, default=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    meeting = relationship("Meeting", back_populates="settings")


class MeetingSecurity(Base):
    __tablename__ = "meeting_security"
    id = Column(Integer, primary_key=True)
    is_private = Column(Boolean, default=True)
    password = Column(String(255), nullable=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    meeting = relationship("Meeting", back_populates="security")


class MeetingRecording(Base):
    __tablename__ = "meeting_recording"
    id = Column(Integer, primary_key=True)
    recording_enabled = Column(Boolean, default=False)
    recording_url = Column(String(255), nullable=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    meeting = relationship("Meeting", back_populates="recording")


class MeetingTranscript(Base):
    __tablename__ = "meeting_transcript"
    id = Column(Integer, primary_key=True)
    transcript = Column(Text, nullable=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    meeting = relationship("Meeting", back_populates="transcript")
