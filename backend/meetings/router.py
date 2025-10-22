from fastapi import APIRouter, Depends, Body, BackgroundTasks
from sqlalchemy.orm import Session
from backend.core.db import get_db
from backend.auth.utils import get_current_user
from backend.models.meeting import Meeting
from backend.scheduler.reminder import schedule_reminder
from backend.email.utils import send_invitation_emails , send_instant_invitation_emails
import uuid, datetime
from backend.core.config import MY_DOMAIN

router = APIRouter()

# -------------------------------------------------------------
# 1️⃣ Schedule Meeting — starts later and sends reminder
# -------------------------------------------------------------
@router.post("/schedule")
def schedule_meeting(
    background_tasks: BackgroundTasks,
    title: str = Body(...),
    agenda: str = Body(None),
    start_time: str = Body(...),
    end_time: str = Body(...),
    participants: list[str] = Body([]),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Schedule a meeting for a future time.
    Sends invitations immediately and schedules a reminder 5 min before.
    """
    start_dt = datetime.datetime.fromisoformat(start_time)
    end_dt = datetime.datetime.fromisoformat(end_time)

    # Unique meeting room
    room_id = str(uuid.uuid4())[:8]
    join_link = f"{MY_DOMAIN}/meeting?room={room_id}"

    # Save to DB
    meeting = Meeting(
        title=title,
        agenda=agenda,
        scheduled_start=start_dt,
        scheduled_end=end_dt,
        attendee_emails=participants,
        meeting_link=join_link,
        room_id=room_id,
        owner_id=current_user.id
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    # Send emails
    if participants:
        background_tasks.add_task(
            send_invitation_emails,
            recipients=participants,
            organizer_email=current_user.email,
            join_link=join_link,
            title=title,
            agenda=agenda,
            start_dt=start_dt
        )
        schedule_reminder(meeting.id, start_dt, participants)

    return {
        "msg": "Meeting scheduled successfully.",
        "meeting_id": meeting.id,
        "join_link": join_link,
        "participants": participants
    }


# -------------------------------------------------------------
# 2️⃣ Instant Meeting — starts right now (no scheduling)
# -------------------------------------------------------------
@router.post("/instant")
def create_instant_meeting(
    background_tasks: BackgroundTasks,
    title: str = Body(...),
    agenda: str = Body(None),
    participants: list[str] = Body([]),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Instantly create a meeting that starts immediately.
    No scheduling or reminder; sends invitations instantly.
    """
    now = datetime.datetime.utcnow()
    end_dt = now + datetime.timedelta(hours=1)  # default 1 hr duration

    room_id = str(uuid.uuid4())[:8]
    join_link = f"{MY_DOMAIN}/meeting?room={room_id}"

    meeting = Meeting(
        title=title,
        agenda=agenda,
        scheduled_start=now,
        scheduled_end=end_dt,
        attendee_emails=participants,
        meeting_link=join_link,
        room_id=room_id,
        owner_id=current_user.id
    )

    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    # Send instant invite
    if participants:
        background_tasks.add_task(
            send_instant_invitation_emails,
            recipients=participants,
            organizer_email=current_user.email,
            join_link=join_link,
            title=title,
            agenda=agenda,
        )

    return {
        "msg": "Instant meeting started successfully.",
        "meeting_id": meeting.id,
        "join_link": join_link,
        "participants": participants
    }
