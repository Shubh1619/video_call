from apscheduler.schedulers.background import BackgroundScheduler
from backend.email.utils import send_meeting_reminder
from backend.core.db import SessionLocal
from backend.models.meeting import Meeting
import datetime
import asyncio

scheduler = BackgroundScheduler()

def schedule_reminder(meeting_id: int, start_dt, recipients: list):
    """
    Schedule a reminder 5 minutes before meeting start.
    """
    reminder_time = start_dt - datetime.timedelta(minutes=5)
    scheduler.add_job(
        send_reminder_job,
        'date',
        run_date=reminder_time,
        args=[meeting_id, recipients],
        misfire_grace_time=600
    )

def send_reminder_job(meeting_id: int, recipients: list):
    """
    Called by APScheduler in background to send reminder.
    """
    db = SessionLocal()
    try:
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if meeting:
            asyncio.run(send_meeting_reminder(
                recipients,
                meeting.owner,
                meeting.meeting_link,
                meeting.title,
                meeting.agenda,
                meeting.scheduled_start
            ))
    finally:
        db.close()

def start_scheduler(app):
    """
    Starts background APScheduler when app starts.
    """
    scheduler.start()
