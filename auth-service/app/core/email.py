from email.message import EmailMessage
import logging
import smtplib
from urllib.parse import quote

from app.core.config import settings

logger = logging.getLogger(__name__)


def build_password_reset_link(token: str) -> str:
    """Build password reset URL sent to users."""
    base_url = settings.SERVICE_PUBLIC_BASE_URL.rstrip("/")
    path = settings.PASSWORD_RESET_LINK_PATH
    if not path.startswith("/"):
        path = f"/{path}"
    encoded_token = quote(token, safe="")
    return f"{base_url}{path}?token={encoded_token}"


def _send_email_sync(to_email: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to_email
    msg.set_content(body)

    if settings.EMAIL_USE_SSL:
        with smtplib.SMTP_SSL(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=10) as smtp:
            if settings.EMAIL_USERNAME and settings.EMAIL_PASSWORD:
                smtp.login(settings.EMAIL_USERNAME, settings.EMAIL_PASSWORD)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=10) as smtp:
        if settings.EMAIL_USE_TLS:
            smtp.starttls()
        if settings.EMAIL_USERNAME and settings.EMAIL_PASSWORD:
            smtp.login(settings.EMAIL_USERNAME, settings.EMAIL_PASSWORD)
        smtp.send_message(msg)


async def send_password_reset_email(to_email: str, token: str) -> None:
    """Send password reset email, with safe fallback when email is disabled."""
    reset_link = build_password_reset_link(token)

    if not settings.EMAIL_ENABLED:
        logger.info("[PASSWORD_RESET_DEV] email=%s link=%s", to_email, reset_link)
        return

    subject = "EGS Password Reset"
    body = (
        "We received a request to reset your password.\n\n"
        f"Reset your password using this link:\n{reset_link}\n\n"
        "If you did not request this, you can ignore this email."
    )

    try:
        _send_email_sync(to_email, subject, body)
    except Exception:
        logger.exception("Failed to send password reset email to %s", to_email)


async def send_dev_test_email(to_email: str) -> None:
    """Send a simple test email to validate SMTP wiring in dev."""
    subject = "EGS SMTP Test Email"
    body = (
        "This is a development test email from EGS Auth Service.\n\n"
        "If you received this in your Mailpit/MailHog inbox, SMTP wiring is working."
    )

    if not settings.EMAIL_ENABLED:
        logger.info("[EMAIL_TEST_DEV] email=%s subject=%s", to_email, subject)
        return

    try:
        _send_email_sync(to_email, subject, body)
    except Exception:
        logger.exception("Failed to send dev test email to %s", to_email)
