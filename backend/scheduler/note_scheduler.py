from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, time, timedelta
import logging
from backend.email.utils import send_note_reminder_email
from backend.email.db import get_db
from backend.models.notes import Note

scheduler = BackgroundScheduler()
scheduler.start()

def schedule_note_reminder(note_id, user_email, note_text, note_date):
    reminder_datetime = datetime.combine(note_date, time(hour=9, minute=0))

    # ignore if time already passed
    if reminder_datetime < datetime.utcnow():
        return

    scheduler.add_job(
        send_note_reminder_email,
        "date",
        run_date=reminder_datetime,
        args=[user_email, note_text, note_date],
        id=f"note_{note_id}",
        replace_existing=True
    )
