from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable

from backend.services.time_service import (
    APP_TIMEZONE_NAME,
    compute_meeting_flags,
    ensure_utc,
    to_app_timezone,
)


def serialize_meeting(meeting, now_utc: datetime | None = None, role: str | None = None) -> dict:
    start_dt = ensure_utc(getattr(meeting, "scheduled_start", None))
    end_dt = ensure_utc(getattr(meeting, "scheduled_end", None))
    local_start = to_app_timezone(start_dt)
    local_end = to_app_timezone(end_dt)
    is_upcoming, is_live, status = compute_meeting_flags(start_dt, end_dt, now_utc)

    owner = getattr(meeting, "owner", None)
    owner_name = owner.name if owner and getattr(owner, "name", None) else None
    owner_email = owner.email if owner and getattr(owner, "email", None) else None

    return {
        "id": meeting.id,
        "meeting_id": meeting.id,
        "title": meeting.title,
        "agenda": meeting.agenda,
        "scheduled_start": start_dt.isoformat() if start_dt else None,
        "scheduled_end": end_dt.isoformat() if end_dt else None,
        "local_start": local_start.isoformat() if local_start else None,
        "local_end": local_end.isoformat() if local_end else None,
        "meeting_timezone": APP_TIMEZONE_NAME,
        "status": status,
        "is_live": is_live,
        "is_upcoming": is_upcoming,
        "time": local_start.strftime("%I:%M %p") if local_start else None,
        "room_id": getattr(meeting, "room_id", None),
        "meeting_link": getattr(meeting, "meeting_link", None),
        "meeting_type": getattr(meeting, "meeting_type", None),
        "owner_id": getattr(meeting, "owner_id", None),
        "owner_name": owner_name,
        "owner_email": owner_email,
        "role": role,
        "can_delete": bool(
            getattr(meeting, "meeting_type", None) == "regular"
            and role == "owner"
        ),
    }


def group_meetings_by_local_date(meetings: Iterable, now_utc: datetime | None = None, role_resolver=None) -> dict[str, list[dict]]:
    grouped = defaultdict(list)

    for meeting in meetings:
        role = role_resolver(meeting) if role_resolver else None
        serialized = serialize_meeting(meeting, now_utc=now_utc, role=role)
        local_start = serialized.get("local_start")

        if local_start:
            date_key = local_start[:10]
        elif serialized.get("scheduled_start"):
            date_key = serialized["scheduled_start"][:10]
        else:
            continue

        grouped[date_key].append(serialized)

    return dict(grouped)
