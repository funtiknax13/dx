import logging
from email.message import EmailMessage
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from app.core.config import settings

logger = logging.getLogger("app.email")

_TEMPLATES_DIR = Path(__file__).parent / "email_templates"
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


def render_email_html(template_name: str, **context: object) -> str:
    return _env.get_template(template_name).render(**context)


async def send_email(to: str, subject: str, text_body: str, html_body: str) -> None:
    """Send an email, or log it to stdout when EMAIL_BACKEND=console (dev
    default).

    Deliverability test: try the full HTML (multipart) message first; if the
    server rejects it (Yandex's outbound filter dislikes HTML from a
    low-reputation sender — 554 spam), fall back to a plain-text-only send,
    which is a weaker spam signal. If even plain text doesn't reach external
    domains, the real fix is a transactional email provider (see logs).
    """
    if settings.email_backend == "console":
        logger.info(
            "\n--- EMAIL (console backend) ---\nTo: %s\nSubject: %s\n\n%s\n"
            "-------------------------------",
            to,
            subject,
            text_body,
        )
        return

    for with_html in (True, False):
        message = EmailMessage()
        message["From"] = settings.smtp_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text_body)
        if with_html:
            message.add_alternative(html_body, subtype="html")
        try:
            await aiosmtplib.send(
                message,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_username or None,
                password=settings.smtp_password or None,
                start_tls=True,
            )
            return
        except Exception as exc:
            logger.warning("Email send failed (html=%s) to %s: %s", with_html, to, exc)
            # with_html is False on the final (plain-text) try — nothing left.
            if not with_html:
                raise


def build_frontend_link(path: str, token: str) -> str:
    return f"{settings.frontend_origin}{path}?token={token}"
