from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from backend.core.config import (
    MAIL_USERNAME,
    MAIL_PASSWORD,
    MAIL_FROM,
    MAIL_PORT,
    MAIL_SERVER,
    MAIL_FROM_NAME,
)
from typing import List
import asyncio
import logging

logger = logging.getLogger(__name__)

# ✅ Mail configuration with timeout
conf = ConnectionConfig(
    MAIL_USERNAME=MAIL_USERNAME,
    MAIL_PASSWORD=MAIL_PASSWORD,
    MAIL_FROM=MAIL_FROM,
    MAIL_PORT=MAIL_PORT,
    MAIL_SERVER=MAIL_SERVER,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    MAIL_FROM_NAME=MAIL_FROM_NAME,
    TIMEOUT=5,  # 5 second timeout
)

fm = FastMail(conf)


# ------------------------------
# ✅ Safe Email Sender with Timeout
# ------------------------------
async def safe_send_email(message):
    """Send email with timeout - won't block if SMTP fails."""
    try:
        await asyncio.wait_for(fm.send_message(message), timeout=5.0)
        logger.info("✅ Email sent successfully")
    except asyncio.TimeoutError:
        logger.warning("⚠️ Email sending timed out - skipping")
    except Exception as e:
        logger.warning(f"⚠️ Email sending failed: {str(e)} - skipping")


# ------------------------------
# ✅ Invitation Email
# ------------------------------
async def send_invitation_emails(
    recipients: List[str],
    organizer_email: str,
    join_link: str,
    title: str,
    agenda: str,
    start_dt=None,
    meeting_type="scheduled",  # "instant" or "scheduled"
):
    """
    Sends a meeting invitation email.
    For instant meetings, start_dt is not shown.
    """
    start_time_html = f"<strong>Start Time:</strong> {start_dt}<br>" if meeting_type == "scheduled" and start_dt else ""

    message = MessageSchema(
        subject=f"Meeting Invitation: {title}",
        recipients=recipients,
        body=f"""
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #222;">
    <p>Hello,</p>
    <p>You've been invited to a meeting!</p>

    <p><strong>Organizer:</strong> <a href="mailto:{organizer_email}">{organizer_email}</a><br>
       <strong>Agenda:</strong> {agenda}<br>
       {start_time_html}
       <strong>Join Link:</strong> <a href="{join_link}" style="color:#1a73e8;">Join Meeting</a>
    </p>

    <p>We look forward to your participation!</p>
    <p style="margin-top: 25px;">Best regards,<br><b>AI Meeting Assistant</b></p>
  </body>
</html>
""",
        subtype="html",
    )
    await safe_send_email(message)

# ------------------------------
# ✅ Instant Meeting Email
# ------------------------------

async def send_instant_invitation_emails(
    recipients: List[str],
    organizer_email: str,
    join_link: str,
    title: str,
    agenda: str,
):
    """
    Sends an instant meeting invitation email.
    """
    message = MessageSchema(
        subject=f"Instant Meeting Invitation: {title}",
        recipients=recipients,
        body=f"""
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #222;">
    <p>Hello,</p>
    <p>You've been invited to an instant meeting!</p>
    <p><strong>Organizer:</strong> <a href="mailto:{organizer_email}">{organizer_email}</a><br>
        <strong>Agenda:</strong> {agenda}<br>
        <strong>Join Link:</strong> <a href="{join_link}" style="color:#1a73e8;">Join Meeting</a>  
    </p>
    <p>Join the meeting right away!</p>
    <p style="margin-top: 25px;">Best regards,<br><b>AI Meeting Assistant</b></p>
  </body>
</html>""",
        subtype="html",
    )
    await safe_send_email(message)

# ------------------------------
# ✅ Reminder Email (Scheduled Only)
# ------------------------------
async def send_meeting_reminder(
    recipients: List[str],
    organizer_email: str,
    join_link: str,
    title: str,
    agenda: str,
    start_dt,
    meeting_type="scheduled",
):
    """
    Sends a reminder email 5 minutes before scheduled meetings.
    Instant meetings do not send reminders.
    """
    if meeting_type != "scheduled" or not start_dt:
        return  # skip for instant meetings

    message = MessageSchema(
        subject=f"Reminder: {title} starts soon!",
        recipients=recipients,
        body=f"""
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #222;">
    <p>Hello,</p>
    <p>This is a friendly reminder for your upcoming meeting.</p>

    <p><strong>Organizer:</strong> <a href="mailto:{organizer_email}">{organizer_email}</a><br>
       <strong>Agenda:</strong> {agenda}<br>
       <strong>Start Time:</strong> {start_dt}<br>
       <strong>Join Link:</strong> <a href="{join_link}" style="color:#1a73e8;">Join Meeting</a>
    </p>

    <p>Please be ready on time!</p>
    <p style="margin-top: 25px;">Best regards,<br><b>AI Meeting Assistant</b></p>
  </body>
</html>
""",
        subtype="html",
    )
    await safe_send_email(message)

# ------------------------------
# ✅ Reminder Email (Scheduled Only)
# ------------------------------
async def send_meeting_reminder(
    recipients: List[str],
    organizer_email: str,
    join_link: str,
    title: str,
    agenda: str,
    start_dt,
    meeting_type="scheduled",
):
    """
    Sends a reminder email 5 minutes before scheduled meetings.
    Instant meetings do not send reminders.
    """
    if meeting_type != "scheduled" or not start_dt:
        return  # skip for instant meetings

    message = MessageSchema(
        subject=f"Reminder: {title} starts soon!",
        recipients=recipients,
        body=f"""
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #222;">
    <p>Hello,</p>
    <p>This is a friendly reminder for your upcoming meeting.</p>

    <p><strong>Organizer:</strong> <a href="mailto:{organizer_email}">{organizer_email}</a><br>
       <strong>Agenda:</strong> {agenda}<br>
       <strong>Start Time:</strong> {start_dt}<br>
       <strong>Join Link:</strong> <a href="{join_link}" style="color:#1a73e8;">Join Meeting</a>
    </p>

    <p>Please be ready on time!</p>
    <p style="margin-top: 25px;">Best regards,<br><b>AI Meeting Assistant</b></p>
  </body>
</html>
""",
        subtype="html",
    )
    await safe_send_email(message)




async def send_note_reminder_email_async(email: str, note_text: str, note_date: str):
    """
    Sends a reminder email for a note scheduled for a specific date.
    """
    try:
        message = MessageSchema(
            subject=f"Note Reminder: {note_date}",
            recipients=[email],
            body=f"""
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #222;">
    <p>Hello,</p>
    <p>This is a reminder for your scheduled note:</p>
    
    <div style="background-color: #f5f5f5; padding: 15px; border-radius: 8px; margin: 15px 0;">
      <p style="margin: 0;"><strong>Date:</strong> {note_date}</p>
      <p style="margin: 10px 0 0 0;"><strong>Note:</strong></p>
      <p style="margin: 5px 0 0 0; font-style: italic;">{note_text}</p>
    </div>
    
    <p>Don't forget to review your note!</p>
    <p style="margin-top: 25px;">Best regards,<br><b>AI Meeting Assistant</b></p>
  </body>
</html>
""",
            subtype="html",
        )
        await safe_send_email(message)
        logger.info(f"Note reminder sent to {email} for date {note_date}")
        return True
    except Exception as e:
        logger.warning(f"Failed to send note reminder to {email}: {e}")
        return False


def send_note_reminder_email(email: str, note: str, note_date):
    """
    Synchronous wrapper for note reminder email.
    Used by APScheduler which calls synchronous functions.
    """
    import asyncio
    
    note_date_str = note_date.isoformat() if hasattr(note_date, 'isoformat') else str(note_date)
    
    try:
        asyncio.run(send_note_reminder_email_async(email, note, note_date_str))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(send_note_reminder_email_async(email, note, note_date_str))
        finally:
            loop.close()


def meeting_to_dict(m):
    return {
        "id": m.id,
        "title": m.title,
        "agenda": m.agenda,
        "scheduled_start": m.scheduled_start.isoformat() if m.scheduled_start is not None else None,
        "scheduled_end": m.scheduled_end.isoformat() if m.scheduled_end is not None else None,
        "meeting_link": m.meeting_link,
        "meeting_type": m.meeting_type,
        "room_id": m.room_id,
        "owner_id": m.owner_id,
    }
