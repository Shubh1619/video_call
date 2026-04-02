import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from backend.core.config import MAIL_CONFIG
from typing import List
import asyncio
import logging

logger = logging.getLogger(__name__)

# ------------------------------
# âœ… BREVO CONFIG
# ------------------------------
configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = MAIL_CONFIG.get("BREVO_API_KEY")

api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
    sib_api_v3_sdk.ApiClient(configuration)
)

# ------------------------------
# âœ… SAFE EMAIL SENDER (BREVO)
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
        logger.info("âœ… Email sent via Brevo")

    except ApiException as e:
        logger.error(f"âŒ Brevo error: {e}")


# ------------------------------
# âœ… COMMON HTML TEMPLATE
# ------------------------------
def build_email_template(title, subtitle, content_html, button_link=None, button_text=None, color="#1a73e8"):
    cta_html = ""
    if button_link and button_text:
        cta_html = f"""
                <div style="text-align:center;margin:30px 0;">
                  <a href="{button_link}" 
                     style="background:{color};color:white;padding:14px 28px;
                            text-decoration:none;border-radius:6px;
                            font-weight:bold;">
                     {button_text}
                  </a>
                </div>
        """
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
                {cta_html}
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
# âœ… INSTANT MEETING EMAIL
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
    <p>Youâ€™ve been invited to an instant meeting.</p>
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
# âœ… SCHEDULED MEETING EMAIL
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
    <p>Youâ€™ve been invited to a meeting.</p>
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
# âœ… MEETING REMINDER
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
# âœ… NOTE REMINDER
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
# âœ… SYNC WRAPPER (SCHEDULER)
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


async def send_password_reset_email(
    recipient_email: str,
    recipient_name: str | None,
    reset_link: str,
    app_reset_link: str | None = None,
    expires_minutes: int = 30,
):
    display_name = (recipient_name or "there").strip() or "there"
    content = f"""
    <p>Hello {display_name},</p>
    <p>We received a request to reset your password for your Meeting Platform account.</p>

    <div style="background:#fff4e5;border:1px solid #ffd8a8;border-radius:8px;padding:12px;margin:14px 0;">
      <p style="margin:0 0 8px 0;"><strong>Security Notice</strong></p>
      <p style="margin:0;">This link is valid for <strong>{expires_minutes} minutes</strong> and can be used only once.</p>
    </div>

    <p>If you did not request this change, you can safely ignore this email. Your current password will remain unchanged.</p>
    <p>For your safety, never share this link or token with anyone.</p>
    """
    if app_reset_link:
        content += f"""
        <p style="margin-top:10px;">
          If you're on mobile, you can also open the app link directly:
          <br><a href="{app_reset_link}">{app_reset_link}</a>
        </p>
        """

    html = build_email_template(
        "Password Reset",
        "Reset your password securely",
        content,
        reset_link,
        "Reset Password",
        color="#d93025",
    )

    await safe_send_email([recipient_email], "Reset your password", html)


async def send_email_verification_email(
    recipient_email: str,
    recipient_name: str | None,
    otp_code: str,
    expires_minutes: int = 30,
):
    display_name = (recipient_name or "there").strip() or "there"
    content = f"""
    <p>Hello {display_name},</p>
    <p>Welcome to Meeting Platform. Please verify your email address to activate your account.</p>

    <div style="background:#e9f2ff;border:1px solid #b6d4ff;border-radius:8px;padding:12px;margin:14px 0;">
      <p style="margin:0 0 8px 0;"><strong>Email Verification</strong></p>
      <p style="margin:0;">This OTP is valid for <strong>{expires_minutes} minutes</strong>.</p>
    </div>

    <div style="background:#f6f8fb;border:1px dashed #9bb6ff;border-radius:10px;padding:18px;margin:18px 0;text-align:center;">
      <p style="margin:0 0 8px 0;color:#5b6b83;font-size:12px;letter-spacing:1px;">YOUR OTP CODE</p>
      <p style="margin:0;font-size:30px;font-weight:700;letter-spacing:6px;color:#1a73e8;">{otp_code}</p>
    </div>

    <p>If you did not create this account, you can ignore this email.</p>
    """

    html = build_email_template(
        "Verify Your Email",
        "Enter this OTP in the app",
        content,
        color="#1a73e8",
    )
    await safe_send_email([recipient_email], "Verify your email address", html)


async def send_password_change_verification_email(
    recipient_email: str,
    recipient_name: str | None,
    otp_code: str,
    expires_minutes: int = 15,
):
    display_name = (recipient_name or "there").strip() or "there"
    content = f"""
    <p>Hello {display_name},</p>
    <p>We received a request to change your password. Please confirm this action.</p>

    <div style="background:#fff4e5;border:1px solid #ffd8a8;border-radius:8px;padding:12px;margin:14px 0;">
      <p style="margin:0 0 8px 0;"><strong>Security Notice</strong></p>
      <p style="margin:0;">This OTP is valid for <strong>{expires_minutes} minutes</strong> and can be used only once.</p>
    </div>

    <div style="background:#fff8f2;border:1px dashed #ffb074;border-radius:10px;padding:18px;margin:18px 0;text-align:center;">
      <p style="margin:0 0 8px 0;color:#7a5c45;font-size:12px;letter-spacing:1px;">PASSWORD CHANGE OTP</p>
      <p style="margin:0;font-size:30px;font-weight:700;letter-spacing:6px;color:#d93025;">{otp_code}</p>
    </div>

    <p>If you did not request this password change, ignore this email and keep your account secure.</p>
    """

    html = build_email_template(
        "Confirm Password Change",
        "Enter this OTP in your profile",
        content,
        color="#d93025",
    )
    await safe_send_email([recipient_email], "Confirm your password change", html)
