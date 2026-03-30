from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from backend.auth.utils import get_current_user
from backend.email.db import get_db
from backend.models.meeting import Meeting
from backend.models.user import User
from backend.services.meeting_serializer import group_meetings_by_local_date, serialize_meeting
from backend.services.time_service import get_utc_now, parse_date_to_utc_range, parse_month_to_utc_range

router = APIRouter()


@router.get("/meetings")
def get_meetings_by_date(
    date: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    start_of_day, end_of_day, _ = parse_date_to_utc_range(date)

    meetings = (
        db.query(Meeting)
        .options(joinedload(Meeting.owner))
        .filter(
            Meeting.owner_id == current_user.id,
            Meeting.scheduled_start >= start_of_day,
            Meeting.scheduled_start < end_of_day,
        )
        .all()
    )

    now = get_utc_now()
    return {
        "date": date,
        "meetings": [serialize_meeting(m, now_utc=now, role="owner") for m in meetings],
    }


@router.get("/meetings/dashboard")
def get_dashboard_meetings(
    upcoming_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user_email = (current_user.email or "").strip().lower()
    now = get_utc_now()

    owner_query = (
        db.query(Meeting)
        .options(joinedload(Meeting.owner))
        .filter(Meeting.owner_id == current_user.id)
    )
    participant_query = (
        db.query(Meeting)
        .options(joinedload(Meeting.owner))
        .filter(Meeting.attendee_emails.any(user_email))
    )

    if upcoming_only:
        owner_query = owner_query.filter(Meeting.scheduled_end >= now)
        participant_query = participant_query.filter(Meeting.scheduled_end >= now)

    owner_meetings = owner_query.all()
    participant_meetings = participant_query.all()

    merged_by_id = {meeting.id: meeting for meeting in owner_meetings + participant_meetings}
    all_meetings = list(merged_by_id.values())
    all_meetings.sort(key=lambda meeting: meeting.scheduled_start or datetime.max.replace(tzinfo=timezone.utc))

    def _role_resolver(meeting: Meeting) -> str:
        return "owner" if meeting.owner_id == current_user.id else "participant"

    return group_meetings_by_local_date(all_meetings, now_utc=now, role_resolver=_role_resolver)


@router.get("/user/{user_id}")
def get_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"error": "User not found"}
    return {"id": user.id, "name": user.name, "email": user.email}


@router.get("/meetings/by-month")
def get_meetings_by_month(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    start_date, end_date = parse_month_to_utc_range(year, month)

    meetings = (
        db.query(Meeting)
        .options(joinedload(Meeting.owner))
        .filter(
            Meeting.owner_id == current_user.id,
            Meeting.scheduled_start >= start_date,
            Meeting.scheduled_start < end_date,
        )
        .all()
    )

    now = get_utc_now()
    serialized = [serialize_meeting(m, now_utc=now, role="owner") for m in meetings]

    return {
        "dates": [m["local_start"][:10] if m.get("local_start") else None for m in serialized],
        "meetings": [{"id": m["id"], "date": m["local_start"][:10] if m.get("local_start") else None} for m in serialized],
        "items": serialized,
    }


@router.get("/meetings/month")
def get_meetings_by_month_compat(
    month: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        year, mon = map(int, month.split("-"))
    except (ValueError, AttributeError):
        return {"dates": [], "meetings": [], "items": []}
    return get_meetings_by_month(year, mon, db, current_user)
