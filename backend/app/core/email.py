import base64
import logging
from email.message import EmailMessage
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from app.core.config import settings

logger = logging.getLogger("app.email")

_TEMPLATES_DIR = Path(__file__).parent / "email_templates"
_ASSETS_DIR = _TEMPLATES_DIR / "assets"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _nl2br(value: str) -> Markup:
    """Jinja filter: escape then turn newlines into <br> — used for rendering
    free-text (e.g. a support reply) inside an HTML email, where CSS
    white-space handling is unreliable across mail clients."""
    return Markup("<br>\n".join(str(escape(value)).split("\n")))


_env.filters["nl2br"] = _nl2br


def _data_uri(filename: str) -> str:
    """Base64 data URI for a brand asset — embedded directly in every email
    rather than linked, since there's no public static-file host set up for
    the backend yet (only /media, for user-uploaded content)."""
    content = (_ASSETS_DIR / filename).read_bytes()
    return f"data:image/png;base64,{base64.b64encode(content).decode('ascii')}"


# Computed once at import time, not per-email — the files never change at runtime.
_LOGO_MARK_URI = _data_uri("logo-mark-square.png")
_LOGO_FULL_URI = _data_uri("logo-full-light.png")


def render_email_html(template_name: str, **context: object) -> str:
    return _env.get_template(template_name).render(
        logo_mark_uri=_LOGO_MARK_URI,
        logo_full_uri=_LOGO_FULL_URI,
        **context,
    )


async def send_email(to: str, subject: str, text_body: str, html_body: str) -> None:
    """Send a text+HTML email, or log the text part to stdout when
    EMAIL_BACKEND=console (dev default)."""
    if settings.email_backend == "console":
        logger.info(
            "\n--- EMAIL (console backend) ---\nTo: %s\nSubject: %s\n\n%s\n"
            "-------------------------------",
            to,
            subject,
            text_body,
        )
        return

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

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
