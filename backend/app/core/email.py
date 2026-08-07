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


# TEMPORARY (deliverability testing): send plain-text only and retry once on
# failure. HTML is a stronger spam signal, so we're checking whether a bare
# text message gets past Yandex's outbound filter. html_body is kept in the
# signature so re-enabling the HTML alternative is a one-line change. If this
# doesn't reliably deliver to external domains, the real fix is a transactional
# email provider (see the send failures logged here).
_SEND_ATTEMPTS = 2


async def send_email(to: str, subject: str, text_body: str, html_body: str) -> None:
    """Send a plain-text email, or log it to stdout when EMAIL_BACKEND=console
    (dev default). Retries once on failure — see the module note above."""
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

    for attempt in range(1, _SEND_ATTEMPTS + 1):
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
            logger.warning(
                "Email send attempt %d/%d to %s failed: %s", attempt, _SEND_ATTEMPTS, to, exc
            )
            if attempt == _SEND_ATTEMPTS:
                raise


def build_frontend_link(path: str, token: str) -> str:
    return f"{settings.frontend_origin}{path}?token={token}"
