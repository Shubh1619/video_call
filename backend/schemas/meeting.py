from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

class MeetingSettingsSchema(BaseModel):
    max_participants: Optional[int] = 100
    chat_enabled: Optional[bool] = True
    screen_share_enabled: Optional[bool] = True

class MeetingSecuritySchema(BaseModel):
    is_private: Optional[bool] = True
    password: Optional[str] = None

class MeetingRecordingSchema(BaseModel):
    recording_enabled: Optional[bool] = False
    recording_url: Optional[str] = None

class MeetingTranscriptSchema(BaseModel):
    transcript: Optional[str] = None

class MeetingCreate(BaseModel):
    title: str
    agenda: Optional[str] = None
    scheduled_start: datetime
    scheduled_end: datetime
    settings: Optional[MeetingSettingsSchema] = None
    security: Optional[MeetingSecuritySchema] = None
    recording: Optional[MeetingRecordingSchema] = None
    transcript: Optional[str] = None

class MeetingResponse(BaseModel):
    id: int
    room_id: str
    meeting_link: str
    meeting_url: str
    title: str
    agenda: Optional[str]
    scheduled_start: datetime
    scheduled_end: datetime
    owner_id: int
    status: str
    meeting_type: str
    settings: Optional[MeetingSettingsSchema]
    security: Optional[MeetingSecuritySchema]
    recording: Optional[MeetingRecordingSchema]
    transcript: Optional[str]

    class Config:
        orm_mode = True
