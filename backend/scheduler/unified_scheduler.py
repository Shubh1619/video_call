"""
Unified Scheduler - Consolidates all background tasks into a single scheduler.

Replaces:
- scheduler/reminder.py
- scheduler/cleanup.py
- scheduler/note_scheduler.py
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.core.config import DATABASE_URL
from backend.email.db import SessionLocal
from backend.email.utils import send_meeting_reminder, send_note_reminder_email_async
from backend.models.meeting import Meeting

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_EMAIL_RETRIES = 2
RETRY_DELAY_SECONDS = 60


def _build_scheduler():
    scheduler_kwargs = {
        "timezone": "UTC",
        "job_defaults": {
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 600,
        },
    }
    if DATABASE_URL:
        scheduler_kwargs["jobstores"] = {
            "default": SQLAlchemyJobStore(url=DATABASE_URL)
        }
    else:
        logger.warning("DATABASE_URL is not set. Scheduler persistence is disabled.")
    return BackgroundScheduler(**scheduler_kwargs)


# Single scheduler instance for all tasks
scheduler = _build_scheduler()


def get_utc_now():
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def run_async(coro):
    """Run async coroutine safely from scheduler job threads."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)
    finally:
        loop.close()


def _schedule_retry(job_func, args, job_id: str):
    """
    Schedule a one-off retry after a short delay.
    """
    retry_run_date = get_utc_now() + timedelta(seconds=RETRY_DELAY_SECONDS)
    scheduler.add_job(
        job_func,
        DateTrigger(run_date=retry_run_date),
        args=args,
        id=job_id,
        replace_existing=True,
    )


# -----------------------------
# Meeting Reminder Jobs
# -----------------------------

def schedule_meeting_reminder(meeting_id: int, start_dt, recipients: list | None = None):
    if not start_dt:
        logger.info(f"Skipping meeting reminder for meeting {meeting_id}: missing start time")
        return

    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)

    now = get_utc_now()
    if start_dt <= now:
        logger.info(f"Skipping meeting reminder for meeting {meeting_id}: meeting already started/past")
        return

    reminder_time = start_dt - timedelta(minutes=5)
    run_at = reminder_time if reminder_time > now else now + timedelta(seconds=10)

    if run_at > now:
        scheduler.add_job(
            send_meeting_reminder_job,
            DateTrigger(run_date=run_at),
            args=[meeting_id, recipients or [], 0],
            id=f"meeting_reminder_{meeting_id}",
            replace_existing=True,
            max_instances=1,
        )
        logger.info(
            "Scheduled reminder for meeting %s at %s (start=%s)",
            meeting_id,
            run_at,
            start_dt,
        )
    else:
        logger.info(f"Skipping meeting reminder for meeting {meeting_id}: time already passed")


def _resolve_meeting_recipients(meeting: Meeting, provided_recipients: list | None = None) -> list[str]:
    owner_email = meeting.owner.email if meeting.owner and meeting.owner.email else None
    attendee_emails = meeting.attendee_emails or []
    combined = []
    if owner_email:
        combined.append(owner_email)
    combined.extend(attendee_emails)
    if provided_recipients:
        combined.extend(provided_recipients)

    # Preserve order while removing empty/duplicate values
    unique = list(dict.fromkeys(email.strip() for email in combined if isinstance(email, str) and email.strip()))
    return unique


def send_meeting_reminder_job(meeting_id: int, recipients: list | None = None, retry_count: int = 0):
    """Background job to send meeting reminder email."""
    try:
        with SessionLocal() as db:
            meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
            if not meeting:
                logger.warning(f"Meeting {meeting_id} not found for reminder")
                return

            final_recipients = _resolve_meeting_recipients(meeting, recipients)
            if not final_recipients:
                logger.info(f"Skipping meeting reminder for meeting {meeting_id}: no recipient emails found")
                return

            organizer_email = meeting.owner.email if meeting.owner and meeting.owner.email else "organizer@example.com"

            run_async(
                send_meeting_reminder(
                    final_recipients,
                    organizer_email,
                    meeting.meeting_link,
                    meeting.title,
                    meeting.agenda,
                    meeting.scheduled_start.isoformat() if meeting.scheduled_start else None,
                )
            )
            logger.info(f"Sent reminder for meeting {meeting_id} to {len(final_recipients)} recipients")
    except Exception as exc:
        logger.error(f"Failed to send meeting reminder for meeting {meeting_id}: {exc}")
        if retry_count < MAX_EMAIL_RETRIES:
            next_retry = retry_count + 1
            retry_job_id = f"meeting_reminder_retry_{meeting_id}_{next_retry}"
            _schedule_retry(
                send_meeting_reminder_job,
                [meeting_id, recipients, next_retry],
                retry_job_id,
            )
            logger.info(
                "Scheduled retry %s/%s for meeting reminder %s",
                next_retry,
                MAX_EMAIL_RETRIES,
                meeting_id,
            )


# -----------------------------
# Note Reminder Jobs
# -----------------------------

def schedule_note_reminder(note_id: int, user_email: str, note_text: str, note_date):
    """Schedule a reminder for a note at 9 AM UTC on the note date."""
    reminder_datetime = datetime.combine(note_date, datetime.min.time())
    reminder_datetime = reminder_datetime.replace(hour=9, minute=0, second=0)
    reminder_datetime_utc = reminder_datetime.replace(tzinfo=timezone.utc)

    if reminder_datetime_utc > get_utc_now():
        scheduler.add_job(
            send_note_reminder_job,
            DateTrigger(run_date=reminder_datetime_utc),
            args=[note_id, user_email, note_text, note_date.isoformat(), 0],
            id=f"note_reminder_{note_id}",
            replace_existing=True,
            max_instances=1,
        )
        logger.info(f"Scheduled note reminder for note {note_id} at {reminder_datetime_utc}")
    else:
        logger.info(f"Skipping note reminder for note {note_id}: time already passed")


def send_note_reminder_job(
    note_id: int,
    user_email: str,
    note_text: str,
    note_date_str: str,
    retry_count: int = 0,
):
    """Background job to send note reminder email."""
    try:
        run_async(send_note_reminder_email_async(user_email, note_text, note_date_str))
        logger.info(f"Sent note reminder to {user_email}")
    except Exception as exc:
        logger.error(f"Failed to send note reminder for note {note_id}: {exc}")
        if retry_count < MAX_EMAIL_RETRIES:
            next_retry = retry_count + 1
            retry_job_id = f"note_reminder_retry_{note_id}_{next_retry}"
            _schedule_retry(
                send_note_reminder_job,
                [note_id, user_email, note_text, note_date_str, next_retry],
                retry_job_id,
            )
            logger.info(
                "Scheduled retry %s/%s for note reminder %s",
                next_retry,
                MAX_EMAIL_RETRIES,
                note_id,
            )


# -----------------------------
# Cleanup Jobs
# -----------------------------

def delete_expired_meetings():
    """
    Delete expired meetings:
    - Instant meetings older than 2 hours
    - Scheduled meetings 30 minutes after end time
    """
    now = get_utc_now()

    try:
        with SessionLocal() as db:
            instant_expired = db.query(Meeting).filter(
                Meeting.meeting_type == "instant",
                Meeting.scheduled_start <= now - timedelta(hours=2),
            ).all()

            scheduled_expired = db.query(Meeting).filter(
                Meeting.meeting_type == "regular",
                Meeting.scheduled_end <= now - timedelta(minutes=30),
            ).all()

            to_delete = instant_expired + scheduled_expired
            count = len(to_delete)

            for meeting in to_delete:
                db.delete(meeting)

            db.commit()

            if count > 0:
                logger.info(
                    "Deleted %s expired meetings (instant: %s, scheduled: %s)",
                    count,
                    len(instant_expired),
                    len(scheduled_expired),
                )
            else:
                logger.info("No expired meetings to delete")
    except Exception as exc:
        logger.error(f"Cleanup error: {exc}")


def cleanup_orphaned_scheduled_jobs():
    """
    Cleanup scheduled jobs that no longer have valid meetings.
    Runs every hour to clean up orphaned reminder jobs.
    """
    try:
        with SessionLocal() as db:
            reminder_jobs = [job for job in scheduler.get_jobs() if job.id.startswith("meeting_reminder_")]

            for job in reminder_jobs:
                meeting_id = int(job.id.replace("meeting_reminder_", ""))
                meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

                if not meeting:
                    job.remove()
                    logger.info(f"Removed orphaned job for meeting {meeting_id}")
    except Exception as exc:
        logger.error(f"Failed to cleanup orphaned jobs: {exc}")


# -----------------------------
# Scheduler Lifecycle
# -----------------------------

def start_all_schedulers():
    """Start all background jobs with a single scheduler instance."""
    if scheduler.running:
        logger.info("Scheduler already running, skipping start")
        return

    scheduler.add_job(
        delete_expired_meetings,
        IntervalTrigger(minutes=5),
        id="cleanup_expired_meetings",
        replace_existing=True,
        misfire_grace_time=600,
    )

    scheduler.add_job(
        cleanup_orphaned_scheduled_jobs,
        IntervalTrigger(hours=1),
        id="cleanup_orphaned_jobs",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info("Unified scheduler started with all jobs")


def shutdown_all_schedulers():
    """Gracefully shutdown all scheduled jobs."""
    if scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler shut down successfully")


def get_scheduler_status():
    """Get current scheduler status and job list."""
    return {
        "running": scheduler.running,
        "jobs": [
            {
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
            for job in scheduler.get_jobs()
        ],
    }
