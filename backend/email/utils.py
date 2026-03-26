from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from backend.core.config import MAIL_CONFIG
from typing import List
import asyncio
import logging

logger = logging.getLogger(__name__)

# ------------------------------
# ✅ MAIL CONFIG
# ------------------------------
conf = ConnectionConfig(
    MAIL_USERNAME=MAIL_CONFIG["MAIL_USERNAME"],
    MAIL_PASSWORD=MAIL_CONFIG["MAIL_PASSWORD"],
    MAIL_FROM=MAIL_CONFIG["MAIL_FROM"],
    MAIL_PORT=MAIL_CONFIG["MAIL_PORT"],
    MAIL_SERVER=MAIL_CONFIG["MAIL_SERVER"],
    MAIL_STARTTLS=MAIL_CONFIG["MAIL_STARTTLS"],
    MAIL_SSL_TLS=MAIL_CONFIG["MAIL_SSL_TLS"],
    USE_CREDENTIALS=MAIL_CONFIG["USE_CREDENTIALS"],
    MAIL_FROM_NAME=MAIL_CONFIG["MAIL_FROM_NAME"],
    TIMEOUT=60,
)

fm = FastMail(conf)


# ------------------------------
# ✅ SAFE EMAIL SENDER
# ------------------------------
async def safe_send_email(message):
    try:
        await asyncio.wait_for(fm.send_message(message), timeout=30.0)
        logger.info("✅ Email sent successfully")
    except asyncio.TimeoutError:
        logger.warning("⚠️ Email timeout - skipping")
    except Exception as e:
        logger.warning(f"⚠️ Email failed: {str(e)}")


# ------------------------------
# ✅ INSTANT MEETING EMAIL
# ------------------------------
async def send_instant_invitation_emails(
    recipients: List[str],
    organizer_email: str,
    join_link: str,
    title: str,
    agenda: str,
):
    if not join_link:
        logger.warning("Join link missing!")
        return

    message = MessageSchema(
        subject=f"Instant Meeting Invitation: {title}",
        recipients=recipients,
        body=f"""
<html>
  <body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial, sans-serif;">
    <table width="100%" style="padding:20px;">
      <tr>
        <td align="center">
          <table width="500" style="background:white;border-radius:10px;padding:25px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
            
            <tr>
              <td style="text-align:center;">
                <h2 style="margin:0;color:#1a73e8;">Meeting Invitation</h2>
                <p style="color:#666;">You're invited to join instantly</p>
              </td>
            </tr>

            <tr>
              <td style="font-size:14px;color:#333;line-height:1.6;">
                <p>Hello,</p>
                <p>You’ve been invited to an instant meeting.</p>

                <p><strong>Organizer:</strong> {organizer_email}<br>
                   <strong>Agenda:</strong> {agenda}</p>

                <div style="text-align:center;margin:30px 0;">
                  <a href="{join_link}" 
                     style="background:#1a73e8;color:white;padding:14px 28px;
                            text-decoration:none;border-radius:6px;
                            font-weight:bold;">
                     Join Meeting
                  </a>
                </div>

                <p style="color:#555;">Click above to join immediately.</p>
              </td>
            </tr>

            <tr>
              <td style="border-top:1px solid #eee;text-align:center;font-size:12px;color:#888;padding-top:10px;">
                This is an automated email. Please do not reply.
              </td>
            </tr>

          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
""",
        subtype="html",
    )

    await safe_send_email(message)


# ------------------------------
# ✅ SCHEDULED MEETING EMAIL
# ------------------------------
async def send_invitation_emails(
    recipients: List[str],
    organizer_email: str,
    join_link: str,
    title: str,
    agenda: str,
    start_dt=None,
):
    message = MessageSchema(
        subject=f"Meeting Invitation: {title}",
        recipients=recipients,
        body=f"""
<html>
  <body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial, sans-serif;">
    <table width="100%" style="padding:20px;">
      <tr>
        <td align="center">
          <table width="500" style="background:white;border-radius:10px;padding:25px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
            
            <tr>
              <td style="text-align:center;">
                <h2 style="margin:0;color:#1a73e8;">Meeting Scheduled</h2>
                <p style="color:#666;">Your meeting details</p>
              </td>
            </tr>

            <tr>
              <td style="font-size:14px;color:#333;line-height:1.6;">
                <p>Hello,</p>

                <p>You’ve been invited to a meeting.</p>

                <p><strong>Organizer:</strong> {organizer_email}<br>
                   <strong>Agenda:</strong> {agenda}<br>
                   <strong>Start Time:</strong> {start_dt}</p>

                <div style="text-align:center;margin:30px 0;">
                  <a href="{join_link}" 
                     style="background:#1a73e8;color:white;padding:14px 28px;
                            text-decoration:none;border-radius:6px;
                            font-weight:bold;">
                     Join Meeting
                  </a>
                </div>
              </td>
            </tr>

            <tr>
              <td style="border-top:1px solid #eee;text-align:center;font-size:12px;color:#888;padding-top:10px;">
                This is an automated email. Please do not reply.
              </td>
            </tr>

          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
""",
        subtype="html",
    )

    await safe_send_email(message)


# ------------------------------
# ✅ MEETING REMINDER (FIXED)
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
    if meeting_type != "scheduled" or not start_dt:
        return

    message = MessageSchema(
        subject=f"Reminder: {title} starts soon!",
        recipients=recipients,
       body=f"""
<html>
  <body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial, sans-serif;">
    <table width="100%" style="padding:20px;">
      <tr>
        <td align="center">
          <table width="500" style="background:white;border-radius:10px;padding:25px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
            
            <tr>
              <td style="text-align:center;">
                <h2 style="margin:0;color:#34a853;">Meeting Reminder</h2>
              </td>
            </tr>

            <tr>
              <td style="font-size:14px;color:#333;line-height:1.6;">
                <p>Hello,</p>

                <p>Your meeting is starting soon.</p>

                <p><strong>Organizer:</strong> {organizer_email}<br>
                   <strong>Agenda:</strong> {agenda}<br>
                   <strong>Start Time:</strong> {start_dt}</p>

                <div style="text-align:center;margin:30px 0;">
                  <a href="{join_link}" 
                     style="background:#34a853;color:white;padding:14px 28px;
                            text-decoration:none;border-radius:6px;
                            font-weight:bold;">
                     Join Meeting
                  </a>
                </div>
              </td>
            </tr>

            <tr>
              <td style="border-top:1px solid #eee;text-align:center;font-size:12px;color:#888;padding-top:10px;">
                Please be ready on time.
              </td>
            </tr>

          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
""",
        subtype="html",
    )

    await safe_send_email(message)


# ------------------------------
# ✅ NOTE REMINDER
# ------------------------------
async def send_note_reminder_email_async(
    email: str,
    note_text: str,
    note_date: str
):
    message = MessageSchema(
        subject=f"Note Reminder: {note_date}",
        recipients=[email],
        body=f"""
<html>
  <body style="font-family: Arial, sans-serif;">
    <p>Hello,</p>
    <p>This is your scheduled note reminder:</p>

    <div style="background:#f5f5f5;padding:15px;border-radius:8px;">
        <p><strong>Date:</strong> {note_date}</p>
        <p><strong>Note:</strong> {note_text}</p>
    </div>

    <p style="margin-top:20px;"><b>AI Meeting Assistant</b></p>
  </body>
</html>
""",
        subtype="html",
    )

    await safe_send_email(message)


# ------------------------------
# ✅ SYNC WRAPPER (SCHEDULER)
# ------------------------------
def send_note_reminder_email(email: str, note: str, note_date):
    import asyncio

    note_date_str = (
        note_date.isoformat() if hasattr(note_date, "isoformat") else str(note_date)
    )

    try:
        asyncio.run(send_note_reminder_email_async(email, note, note_date_str))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                send_note_reminder_email_async(email, note, note_date_str)
            )
        finally:
            loop.close()


# ------------------------------
# ✅ HELPER
# ------------------------------
def meeting_to_dict(m):
    return {
        "id": m.id,
        "title": m.title,
        "agenda": m.agenda,
        "scheduled_start": m.scheduled_start.isoformat() if m.scheduled_start else None,
        "scheduled_end": m.scheduled_end.isoformat() if m.scheduled_end else None,
        "meeting_link": m.meeting_link,
        "meeting_type": m.meeting_type,
        "room_id": m.room_id,
        "owner_id": m.owner_id,
    }