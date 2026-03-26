import logging
import asyncio
from typing import List

import resend

from backend.core.config import (
    MAIL_FROM,
    MAIL_FROM_NAME,
    RESEND_API_KEY,
)

logger = logging.getLogger(__name__)

resend.api_key = RESEND_API_KEY

SHARED_MEETING_LINK = "https://meet-frontend-4op.pages.dev/meeting/45924b19"


def _send_email(to: List[str], subject: str, html: str) -> bool:
    """Send email via Resend API (synchronous)."""
    if not to:
        logger.warning("No recipients provided, skipping email.")
        return False
    try:
        resend.Emails.send({
            "from": f"{MAIL_FROM_NAME} <{MAIL_FROM}>",
            "to": to,
            "subject": subject,
            "html": html,
        })
        logger.info("Email sent successfully to %s", to)
        return True
    except Exception as e:
        logger.warning("Email sending failed: %s", str(e))
        return False


async def safe_send_email(to: List[str], subject: str, html: str) -> bool:
    """Async wrapper — runs Resend call in a thread so it doesn't block the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _send_email, to, subject, html)


async def send_invitation_emails(
    recipients: List[str],
    organizer_email: str,
    join_link: str,
    title: str,
    agenda: str,
    start_dt=None,
    meeting_type="scheduled",
):
    """Send a meeting invitation email."""
    start_time_html = (
        f"<strong>Start Time:</strong> {start_dt}<br>"
        if meeting_type == "scheduled" and start_dt
        else ""
    )
    html = f"""
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #222;">
    <p>Hello,</p>
    <p>You've been invited to a meeting!</p>
    <p>
      <strong>Organizer:</strong> <a href="mailto:{organizer_email}">{organizer_email}</a><br>
      <strong>Agenda:</strong> {agenda}<br>
      {start_time_html}
      <strong>Join Link:</strong> <a href="{join_link}" style="color:#1a73e8;">Join Meeting</a>
    </p>
    <p>We look forward to your participation!</p>
    <p style="margin-top: 25px;">Best regards,<br><b>AI Meeting Assistant</b></p>
  </body>
</html>
"""
    await safe_send_email(recipients, f"Meeting Invitation: {title}", html)


async def send_instant_invitation_emails(
    recipients: List[str],
    organizer_email: str,
    join_link: str,
    title: str,
    agenda: str,
):
    """Send an instant meeting invitation email."""
    html = f"""
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #222;">
    <p>Hello,</p>
    <p>You've been invited to an instant meeting!</p>
    <p>
      <strong>Organizer:</strong> <a href="mailto:{organizer_email}">{organizer_email}</a><br>
      <strong>Agenda:</strong> {agenda}<br>
      <strong>Join Link:</strong> <a href="{join_link}" style="color:#1a73e8;">Join Meeting</a>
    </p>
    <p>Join the meeting right away!</p>
    <p style="margin-top: 25px;">Best regards,<br><b>AI Meeting Assistant</b></p>
  </body>
</html>
"""
    await safe_send_email(recipients, f"Instant Meeting Invitation: {title}", html)


async def send_meeting_reminder(
    recipients: List[str],
    organizer_email: str,
    join_link: str,
    title: str,
    agenda: str,
    start_dt,
    meeting_type="scheduled",
):
    """Send a reminder email for scheduled meetings."""
    if meeting_type != "scheduled" or not start_dt:
        return
    html = f"""
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #222;">
    <p>Hello,</p>
    <p>This is a friendly reminder for your upcoming meeting.</p>
    <p>
      <strong>Organizer:</strong> <a href="mailto:{organizer_email}">{organizer_email}</a><br>
      <strong>Agenda:</strong> {agenda}<br>
      <strong>Start Time:</strong> {start_dt}<br>
      <strong>Join Link:</strong> <a href="{join_link}" style="color:#1a73e8;">Join Meeting</a>
    </p>
    <p>Please be ready on time!</p>
    <p style="margin-top: 25px;">Best regards,<br><b>AI Meeting Assistant</b></p>
  </body>
</html>
"""
    await safe_send_email(recipients, f"Reminder: {title} starts soon!", html)


async def send_note_reminder_email_async(email: str, note_text: str, note_date: str) -> bool:
    """Send a reminder email for a note scheduled on a specific date."""
    html = f"""
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
"""
    result = await safe_send_email([email], f"Note Reminder: {note_date}", html)
    if result:
        logger.info("Note reminder sent to %s for date %s", email, note_date)
    return result


def send_note_reminder_email(email: str, note: str, note_date):
    """Synchronous wrapper for APScheduler."""
    note_date_str = note_date.isoformat() if hasattr(note_date, "isoformat") else str(note_date)
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