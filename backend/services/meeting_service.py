import uuid
from sqlalchemy.orm import Session
from backend.models.meeting import Meeting, MeetingSettings, MeetingSecurity, MeetingRecording, MeetingTranscript
from backend.models.user import User
from datetime import datetime

def create_meeting(db: Session, creator: User, title: str, agenda: str, scheduled_start: datetime, scheduled_end: datetime, settings: dict = None, security: dict = None, recording: dict = None, transcript: str = None):
    room_id = str(uuid.uuid4())[:8]
    meeting_link = f"/meeting/{room_id}"
    meeting_url = f"/meeting/{room_id}/static"

    meeting_settings = MeetingSettings(**(settings or {}))
    meeting_security = MeetingSecurity(**(security or {}))
    meeting_recording = MeetingRecording(**(recording or {}))
    meeting_transcript = MeetingTranscript(transcript=transcript)

    db.add(meeting_settings)
    db.add(meeting_security)
    db.add(meeting_recording)
    db.add(meeting_transcript)
    db.flush()

    meeting = Meeting(
        title=title,
        agenda=agenda,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        owner_id=creator.id,
        meeting_link=meeting_link,
        meeting_url=meeting_url,
        room_id=room_id,
        settings_id=meeting_settings.id,
        security_id=meeting_security.id,
        recording_id=meeting_recording.id,
        transcript_id=meeting_transcript.id
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting
