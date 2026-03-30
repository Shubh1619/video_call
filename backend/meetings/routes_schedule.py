import uuid
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Request
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.auth.utils import get_current_user
from backend.core.config import MY_DOMAIN, SECRET_KEY
from backend.email.db import get_db
from backend.email.utils import send_instant_invitation_emails, send_invitation_emails
from backend.meetings.common import get_meeting_settings
from backend.models.meeting import Meeting
from backend.models.user import User
from backend.scheduler.unified_scheduler import schedule_meeting_reminder
from backend.services.meeting_serializer import serialize_meeting
from backend.services.time_service import get_utc_now, normalize_meeting_window, parse_datetime_to_utc

router = APIRouter()
JWT_ALGORITHM = "HS256"


def _normalize_emails(emails: list[str] | None) -> list[str]:
    emails = emails or []
    return list(dict.fromkeys((email or "").strip().lower() for email in emails if isinstance(email, str) and email.strip()))


@router.post("/schedule")
def schedule_meeting(
    background_tasks: BackgroundTasks,
    title: str = Body(...),
    agenda: str = Body(None),
    start_time: str = Body(...),
    end_time: str = Body(...),
    participants: list[str] = Body([]),
    waiting_room: bool = Body(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    participants = _normalize_emails(participants)
    start_dt = parse_datetime_to_utc(start_time)
    end_dt = parse_datetime_to_utc(end_time)
    start_dt, end_dt = normalize_meeting_window(start_dt, end_dt)

    room_id = str(uuid.uuid4())[:8]
    join_link = f"{MY_DOMAIN}/meeting/{room_id}"

    meeting = Meeting(
        title=title,
        agenda=agenda,
        scheduled_start=start_dt,
        scheduled_end=end_dt,
        attendee_emails=participants,
        meeting_link=join_link,
        room_id=room_id,
        owner_id=current_user.id,
        meeting_type="regular",
    )

    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    settings = get_meeting_settings(db, meeting)
    settings.waiting_room_enabled = waiting_room
    db.commit()

    if participants:
        background_tasks.add_task(
            send_invitation_emails,
            recipients=participants,
            organizer_email=current_user.email,
            join_link=join_link,
            title=title,
            agenda=agenda,
            start_dt=start_dt,
        )

    schedule_meeting_reminder(meeting.id, start_dt, participants)

    payload = serialize_meeting(meeting, now_utc=get_utc_now(), role="owner")
    return {
        "msg": "Scheduled meeting created.",
        "meeting": payload,
        "meeting_id": meeting.id,
        "join_link": join_link,
        "room_id": room_id,
        "participants": participants,
        "waiting_room_enabled": waiting_room,
    }


@router.post("/instant")
def create_instant_meeting(
    request: Request,
    background_tasks: BackgroundTasks,
    title: str = Body(...),
    agenda: str = Body(None),
    host_name: str = Body(None),
    participants: list[str] = Body([]),
    waiting_room: bool = Body(False),
    db: Session = Depends(get_db),
):
    participants = _normalize_emails(participants)
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None

    current_user = None
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
            email = payload.get("sub")
            if email:
                current_user = db.query(User).filter(User.email == email).first()
        except JWTError:
            pass

    now = get_utc_now()
    end_dt = now + timedelta(hours=1)
    room_id = str(uuid.uuid4())[:8]
    join_link = f"{MY_DOMAIN}/meeting/{room_id}"

    if current_user:
        owner_id = current_user.id
        organizer_email = current_user.email
        host_display_name = current_user.name or current_user.email
    else:
        owner_id = None
        organizer_email = host_name or "guest@meetify"
        host_display_name = host_name or "Guest Host"

    meeting = Meeting(
        title=title,
        agenda=agenda,
        scheduled_start=now,
        scheduled_end=end_dt,
        attendee_emails=participants,
        meeting_link=join_link,
        room_id=room_id,
        owner_id=owner_id,
        meeting_type="instant",
    )

    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    settings = get_meeting_settings(db, meeting)
    settings.waiting_room_enabled = waiting_room
    db.commit()

    from backend.services.guest_session import guest_session_manager

    session_id, guest_token = guest_session_manager.create_guest_session(
        room_id=room_id,
        name=host_display_name,
        user_id=owner_id,
        is_host=True,
    )

    if participants:
        background_tasks.add_task(
            send_instant_invitation_emails,
            recipients=participants,
            organizer_email=organizer_email,
            join_link=join_link,
            title=title,
            agenda=agenda,
        )

    payload = serialize_meeting(meeting, now_utc=now, role="owner" if owner_id else "participant")
    return {
        "msg": "Instant meeting started.",
        "meeting": payload,
        "meeting_id": meeting.id,
        "join_link": join_link,
        "room_id": room_id,
        "participants": participants,
        "waiting_room_enabled": waiting_room,
        "host_session_id": session_id,
        "host_guest_token": guest_token,
    }
