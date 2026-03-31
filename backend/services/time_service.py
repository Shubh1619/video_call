from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException

APP_TIMEZONE = ZoneInfo("Asia/Kolkata")
APP_TIMEZONE_NAME = "Asia/Kolkata"
MAX_MEETING_DURATION_HOURS = 24


def ensure_utc(dt_obj: datetime | None) -> datetime | None:
    if dt_obj is None:
        return None
    if dt_obj.tzinfo is None:
        return dt_obj.replace(tzinfo=timezone.utc)
    return dt_obj.astimezone(timezone.utc)


def parse_datetime_to_utc(dt_str: str) -> datetime:
    raw = (dt_str or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Datetime value is required")

    normalized = raw.replace("Z", "+00:00")

    try:
        dt_obj = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            dt_obj = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S")
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid datetime format. Use ISO 8601, e.g. 2026-03-30T23:17:00+05:30",
            ) from exc

    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=APP_TIMEZONE)

    return dt_obj.astimezone(timezone.utc)


def normalize_meeting_window(start_dt_utc: datetime, end_dt_utc: datetime) -> tuple[datetime, datetime]:
    start_dt_utc = ensure_utc(start_dt_utc)
    end_dt_utc = ensure_utc(end_dt_utc)

    if end_dt_utc <= start_dt_utc:
        end_dt_utc = end_dt_utc + timedelta(days=1)

    duration = end_dt_utc - start_dt_utc
    if duration <= timedelta(minutes=0):
        raise HTTPException(status_code=400, detail="Meeting end time must be after start time")
    if duration > timedelta(hours=MAX_MEETING_DURATION_HOURS):
        raise HTTPException(
            status_code=400,
            detail=f"Meeting duration cannot exceed {MAX_MEETING_DURATION_HOURS} hours",
        )

    return start_dt_utc, end_dt_utc


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_db_utc_naive(dt_obj: datetime | None) -> datetime | None:
    """
    Convert a datetime to UTC-naive form for SQL filter compatibility.

    Some deployed databases still store meeting timestamps as naive `timestamp`
    values. Binding timezone-aware datetimes in SQL comparisons can raise
    driver-level errors, so we normalize to UTC-naive at query boundaries.
    """
    dt_utc = ensure_utc(dt_obj)
    if dt_utc is None:
        return None
    return dt_utc.replace(tzinfo=None)


def compute_meeting_flags(
    start_dt_utc: datetime | None,
    end_dt_utc: datetime | None,
    now_utc: datetime | None = None,
) -> tuple[bool, bool, str]:
    now = ensure_utc(now_utc) or get_utc_now()
    start = ensure_utc(start_dt_utc)
    end = ensure_utc(end_dt_utc)

    if not start:
        return False, False, "unknown"

    is_live = bool(end and start <= now <= end)
    is_upcoming = bool(start > now)

    if is_live:
        status = "live"
    elif is_upcoming:
        status = "upcoming"
    else:
        status = "ended"

    return is_upcoming, is_live, status


def to_app_timezone(dt_utc: datetime | None) -> datetime | None:
    dt = ensure_utc(dt_utc)
    if not dt:
        return None
    return dt.astimezone(APP_TIMEZONE)


def parse_date_to_utc_range(date_str: str) -> tuple[datetime, datetime, date]:
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD") from exc

    start_local = datetime.combine(target_date, dt_time.min, tzinfo=APP_TIMEZONE)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc), target_date


def parse_month_to_utc_range(year: int, month: int) -> tuple[datetime, datetime]:
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Invalid month")

    start_local = datetime(year, month, 1, tzinfo=APP_TIMEZONE)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=APP_TIMEZONE)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=APP_TIMEZONE)

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
