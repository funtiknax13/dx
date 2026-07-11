import logging
from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger("app.email")


async def send_email(to: str, subject: str, body: str) -> None:
    """Send an email, or log it to stdout when EMAIL_BACKEND=console (dev default)."""
    if settings.email_backend == "console":
        logger.info(
            "\n--- EMAIL (console backend) ---\nTo: %s\nSubject: %s\n\n%s\n"
            "-------------------------------",
            to,
            subject,
            body,
        )
        return

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username or None,
        password=settings.smtp_password or None,
        start_tls=True,
    )


def build_frontend_link(path: str, token: str) -> str:
    return f"{settings.frontend_origin}{path}?token={token}"
