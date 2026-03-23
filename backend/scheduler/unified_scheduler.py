"""
Unified Scheduler - Consolidates all background tasks into a single scheduler.

Replaces:
- scheduler/reminder.py
- scheduler/cleanup.py  
- scheduler/note_scheduler.py
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta, timezone
import logging
import asyncio

from backend.email.db import SessionLocal
from backend.models.meeting import Meeting
from backend.models.notes import Note
from backend.email.utils import send_meeting_reminder, send_note_reminder_email_async

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Single scheduler instance for all tasks
scheduler = BackgroundScheduler(
    timezone="UTC",
    job_defaults={
        'coalesce': True,      # Combine multiple pending executions
        'max_instances': 1,    # Only one instance of each job at a time
        'misfire_grace_time': 600  # 10 minutes grace time for missed jobs
    }
)


def get_utc_now():
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def get_utc_now_naive():
    """Get current UTC time as naive datetime for database comparisons."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# -----------------------------
# Meeting Reminder Jobs
# -----------------------------

def schedule_meeting_reminder(meeting_id: int, start_dt, recipients: list):
    """
    Schedule a reminder 5 minutes before meeting start.
    """
    if start_dt:
        if hasattr(start_dt, 'tzinfo') and start_dt.tzinfo:
            reminder_time = start_dt - timedelta(minutes=5)
        else:
            reminder_time = start_dt - timedelta(minutes=5)
        
        if reminder_time > get_utc_now_naive():
            scheduler.add_job(
                send_meeting_reminder_job,
                DateTrigger(run_date=reminder_time),
                args=[meeting_id, recipients],
                id=f"meeting_reminder_{meeting_id}",
                replace_existing=True
            )
            logger.info(f"Scheduled reminder for meeting {meeting_id} at {reminder_time}")


def send_meeting_reminder_job(meeting_id: int, recipients: list):
    """
    Background job to send meeting reminder email.
    """
    db = SessionLocal()
    try:
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if meeting:
            organizer_email = meeting.owner.email if meeting.owner else "organizer@example.com"
            
            asyncio.run(send_meeting_reminder(
                recipients,
                organizer_email,
                meeting.meeting_link,
                meeting.title,
                meeting.agenda,
                meeting.scheduled_start.isoformat() if meeting.scheduled_start else None
            ))
            logger.info(f"Sent reminder for meeting {meeting_id} to {len(recipients)} recipients")
        else:
            logger.warning(f"Meeting {meeting_id} not found for reminder")
    except Exception as e:
        logger.error(f"Failed to send meeting reminder for meeting {meeting_id}: {e}")
    finally:
        db.close()


# -----------------------------
# Note Reminder Jobs
# -----------------------------

def schedule_note_reminder(note_id: int, user_email: str, note_text: str, note_date):
    """
    Schedule a reminder for a note at 9 AM on the note date.
    """
    reminder_datetime = datetime.combine(note_date, datetime.min.time())
    reminder_datetime = reminder_datetime.replace(hour=9, minute=0, second=0)
    reminder_datetime_utc = reminder_datetime.replace(tzinfo=timezone.utc)
    
    if reminder_datetime_utc > get_utc_now():
        scheduler.add_job(
            send_note_reminder_job,
            DateTrigger(run_date=reminder_datetime_utc),
            args=[note_id, user_email, note_text, note_date.isoformat()],
            id=f"note_reminder_{note_id}",
            replace_existing=False
        )
        logger.info(f"Scheduled note reminder for note {note_id} at {reminder_datetime_utc}")


def send_note_reminder_job(note_id: int, user_email: str, note_text: str, note_date_str: str):
    """
    Background job to send note reminder email.
    """
    try:
        asyncio.run(send_note_reminder_email_async(user_email, note_text, note_date_str))
        logger.info(f"Sent note reminder to {user_email}")
    except Exception as e:
        logger.error(f"Failed to send note reminder for note {note_id}: {e}")


# -----------------------------
# Cleanup Jobs
# -----------------------------

def delete_expired_meetings():
    """
    Delete expired meetings:
    - Instant meetings older than 2 hours
    - Scheduled meetings 30 minutes after end time
    """
    db = SessionLocal()
    now = get_utc_now()
    
    try:
        instant_expired = db.query(Meeting).filter(
            Meeting.meeting_type == "instant",
            Meeting.scheduled_start <= now - timedelta(hours=2)
        ).all()

        scheduled_expired = db.query(Meeting).filter(
            Meeting.meeting_type == "regular",
            Meeting.scheduled_end <= now - timedelta(minutes=30)
        ).all()

        to_delete = instant_expired + scheduled_expired
        count = len(to_delete)

        for m in to_delete:
            db.delete(m)

        db.commit()

        if count > 0:
            logger.info(f"🧹 Deleted {count} expired meetings (instant: {len(instant_expired)}, scheduled: {len(scheduled_expired)})")
        else:
            logger.info("🧹 No expired meetings to delete")

    except Exception as e:
        logger.error(f"❌ Cleanup Error: {e}")
        db.rollback()
    finally:
        db.close()


def cleanup_orphaned_scheduled_jobs():
    """
    Cleanup scheduled jobs that no longer have valid meetings.
    Runs every hour to clean up any orphaned reminder jobs.
    """
    db = SessionLocal()
    try:
        reminder_jobs = [job for job in scheduler.get_jobs() if job.id.startswith("meeting_reminder_")]
        
        for job in reminder_jobs:
            meeting_id = int(job.id.replace("meeting_reminder_", ""))
            meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
            
            if not meeting:
                job.remove()
                logger.info(f"Removed orphaned job for meeting {meeting_id}")
                
    except Exception as e:
        logger.error(f"Failed to cleanup orphaned jobs: {e}")
    finally:
        db.close()


# -----------------------------
# Scheduler Lifecycle
# -----------------------------

def start_all_schedulers():
    """
    Start all background jobs with a single scheduler instance.
    """
    if scheduler.running:
        logger.warning("Scheduler already running")
        return
    
    # Add recurring cleanup job (every 5 minutes)
    scheduler.add_job(
        delete_expired_meetings,
        IntervalTrigger(minutes=5),
        id="cleanup_expired_meetings",
        replace_existing=True,
        misfire_grace_time=600
    )
    
    # Add orphaned job cleanup (every hour)
    scheduler.add_job(
        cleanup_orphaned_scheduled_jobs,
        IntervalTrigger(hours=1),
        id="cleanup_orphaned_jobs",
        replace_existing=True,
        misfire_grace_time=3600
    )
    
    scheduler.start()
    logger.info("✓ Unified scheduler started with all jobs")


def shutdown_all_schedulers():
    """
    Gracefully shutdown all scheduled jobs.
    """
    if scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("✓ Scheduler shut down successfully")


def get_scheduler_status():
    """
    Get current scheduler status and job list.
    """
    return {
        "running": scheduler.running,
        "jobs": [
            {
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            }
            for job in scheduler.get_jobs()
        ]
    }
