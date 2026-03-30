from sqlalchemy.orm import Session

from backend.models.meeting import Meeting, MeetingSettings


def get_meeting_settings(db: Session, meeting: Meeting) -> MeetingSettings:
    settings = db.query(MeetingSettings).filter(MeetingSettings.meeting_id == meeting.id).first()
    if not settings:
        settings = MeetingSettings(
            meeting_id=meeting.id,
            max_participants=100,
            chat_enabled=True,
            screen_share_enabled=True,
            waiting_room_enabled=False,
            allow_guest_join=True,
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings
