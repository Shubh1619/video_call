import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from backend.core.config import MAIL_CONFIG
from typing import List
import asyncio
import logging

logger = logging.getLogger(__name__)

# ------------------------------
# ✅ BREVO CONFIG
# ------------------------------
configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = MAIL_CONFIG.get("BREVO_API_KEY")

api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
    sib_api_v3_sdk.ApiClient(configuration)
)

# ------------------------------
# ✅ SAFE EMAIL SENDER (BREVO)
# ------------------------------
async def safe_send_email(recipients, subject, html):
    try:
        email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": r} for r in recipients],
            sender={
                "name": "Meeting",
                "email": MAIL_CONFIG["MAIL_FROM"]
            },
            subject=subject,
            html_content=html
        )

        api_instance.send_transac_email(email)
        logger.info("✅ Email sent via Brevo")

    except ApiException as e:
        logger.error(f"❌ Brevo error: {e}")


# ------------------------------
# ✅ COMMON HTML TEMPLATE
# ------------------------------
def build_email_template(title, subtitle, content_html, button_link, button_text, color="#1a73e8"):
    return f"""
<html>
  <body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial, sans-serif;">
    <table width="100%" style="padding:20px;">
      <tr>
        <td align="center">
          <table width="500" style="background:white;border-radius:10px;padding:25px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
            
            <tr>
              <td style="text-align:center;">
                <h2 style="margin:0;color:{color};">{title}</h2>
                <p style="color:#666;">{subtitle}</p>
              </td>
            </tr>

            <tr>
              <td style="font-size:14px;color:#333;line-height:1.6;">
                {content_html}

                <div style="text-align:center;margin:30px 0;">
                  <a href="{button_link}" 
                     style="background:{color};color:white;padding:14px 28px;
                            text-decoration:none;border-radius:6px;
                            font-weight:bold;">
                     {button_text}
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
"""


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

    content = f"""
    <p>Hello,</p>
    <p>You’ve been invited to an instant meeting.</p>
    <p><strong>Organizer:</strong> {organizer_email}<br>
       <strong>Agenda:</strong> {agenda}</p>
    """

    html = build_email_template(
        "Meeting Invitation",
        "You're invited to join instantly",
        content,
        join_link,
        "Join Meeting"
    )

    await safe_send_email(recipients, f"Instant Meeting Invitation: {title}", html)


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
    content = f"""
    <p>Hello,</p>
    <p>You’ve been invited to a meeting.</p>
    <p><strong>Organizer:</strong> {organizer_email}<br>
       <strong>Agenda:</strong> {agenda}<br>
       <strong>Start Time:</strong> {start_dt}</p>
    """

    html = build_email_template(
        "Meeting Scheduled",
        "Your meeting details",
        content,
        join_link,
        "Join Meeting"
    )

    await safe_send_email(recipients, f"Meeting Invitation: {title}", html)


# ------------------------------
# ✅ MEETING REMINDER
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

    content = f"""
    <p>Hello,</p>
    <p>Your meeting is starting soon.</p>
    <p><strong>Organizer:</strong> {organizer_email}<br>
       <strong>Agenda:</strong> {agenda}<br>
       <strong>Start Time:</strong> {start_dt}</p>
    """

    html = build_email_template(
        "Meeting Reminder",
        "Starts soon",
        content,
        join_link,
        "Join Meeting",
        color="#34a853"
    )

    await safe_send_email(recipients, f"Reminder: {title} starts soon!", html)


# ------------------------------
# ✅ NOTE REMINDER
# ------------------------------
async def send_note_reminder_email_async(
    email: str,
    note_text: str,
    note_date: str
):
    content = f"""
    <p>Hello,</p>
    <p>This is your scheduled note reminder.</p>

    <div style="background:#f5f5f5;padding:15px;border-radius:8px;">
        <p><strong>Date:</strong> {note_date}</p>
        <p><strong>Note:</strong> {note_text}</p>
    </div>
    """

    html = build_email_template(
        "Note Reminder",
        "",
        content,
        "#",
        "View Note"
    )

    await safe_send_email([email], f"Note Reminder: {note_date}", html)


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