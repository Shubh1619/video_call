import datetime
import logging
from sqlalchemy.orm import Session
from backend.email.db import get_db
from backend.models.meeting import Meeting
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.start()

def delete_expired_meetings():
    db: Session = next(get_db())
    now = datetime.datetime.now(datetime.timezone.utc)

    try:
        # DELETE instant meetings older than 2 hours
        instant_expired = db.query(Meeting).filter(
            Meeting.meeting_type == "instant",
            Meeting.scheduled_start <= now - datetime.timedelta(hours=2)
        ).all()

        # DELETE scheduled (regular) meetings 30 minutes after END time
        scheduled_expired = db.query(Meeting).filter(
            Meeting.meeting_type == "regular",
            Meeting.scheduled_end <= now - datetime.timedelta(minutes=30)
        ).all()

        to_delete = instant_expired + scheduled_expired
        count = len(to_delete)

        for m in to_delete:
            db.delete(m)

        db.commit()
        db.close()

        if count > 0:
            logging.info(f"🧹 Deleted {count} expired meetings (instant: {len(instant_expired)}, scheduled: {len(scheduled_expired)})")

    except Exception as e:
        logging.error(f"❌ Cleanup Error: {e}")
    finally:
        if db:
            db.close()
