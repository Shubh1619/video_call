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

# ✅ Mail configuration
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
)

fm = FastMail(conf)


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
    start_time_html = f"<strong>🕒 Start Time:</strong> {start_dt}<br>" if meeting_type == "scheduled" and start_dt else ""

    message = MessageSchema(
        subject=f"📅 Meeting Invitation: {title}",
        recipients=recipients,
        body=f"""
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #222;">
    <p>Hello 👋,</p>
    <p>You’ve been invited to a meeting!</p>

    <p><strong>🧑‍💼 Organizer:</strong> <a href="mailto:{organizer_email}">{organizer_email}</a><br>
       <strong>📝 Agenda:</strong> {agenda}<br>
       {start_time_html}
       <strong>🔗 Join Link:</strong> <a href="{join_link}" style="color:#1a73e8;">Join Meeting</a>
    </p>

    <p>We look forward to your participation!</p>
    <p style="margin-top: 25px;">Best regards,<br><b>AI Meeting Assistant</b></p>
  </body>
</html>
""",
        subtype="html",
    )
    await fm.send_message(message)

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
        subject=f"🚀 Instant Meeting Invitation: {title}",
        recipients=recipients,
        body=f"""
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #222;">
    <p>Hello 👋,</p>
    <p>You’ve been invited to an instant meeting!</p>
    <p><strong>🧑‍💼 Organizer:</strong> <a href="mailto:{organizer_email}">{organizer_email}</a><br>
        <strong>📝 Agenda:</strong> {agenda}<br>
        <strong>🔗 Join Link:</strong> <a href="{join_link}" style="color:#1a73e8;">Join Meeting</a>  
    </p>
    <p>Join the meeting right away!</p>
    <p style="margin-top: 25px;">Best regards,<br><b> AI Meeting Assistant</b></p>
  </body>
</html>"""
,        subtype="html",
    )
    await fm.send_message(message)

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
        subject=f"⏰ Reminder: {title} starts soon!",
        recipients=recipients,
        body=f"""
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #222;">
    <p>Hello 👋,</p>
    <p>This is a friendly reminder for your upcoming meeting.</p>

    <p><strong>🧑‍💼 Organizer:</strong> <a href="mailto:{organizer_email}">{organizer_email}</a><br>
       <strong>📝 Agenda:</strong> {agenda}<br>
       <strong>🕒 Start Time:</strong> {start_dt}<br>
       <strong>🔗 Join Link:</strong> <a href="{join_link}" style="color:#1a73e8;">Join Meeting</a>
    </p>

    <p>Please be ready on time! 🚀</p>
    <p style="margin-top: 25px;">Best regards,<br><b>AI Meeting Assistant</b></p>
  </body>
</html>
""",
        subtype="html",
    )
    await fm.send_message(message)


