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


async def _send_via(
    to: str,
    subject: str,
    text_body: str,
    html_body: str,
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    from_addr: str,
) -> None:
    """Send through one SMTP transport. Tries the full HTML (multipart) message
    first; if the server rejects it (some outbound filters dislike HTML from a
    low-reputation sender — 554 spam), retries plain-text only, a weaker spam
    signal. Raises if both attempts fail."""
    last_exc: Exception | None = None
    for with_html in (True, False):
        message = EmailMessage()
        message["From"] = from_addr
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text_body)
        if with_html:
            message.add_alternative(html_body, subtype="html")
        try:
            await aiosmtplib.send(
                message,
                hostname=host,
                port=port,
                username=username or None,
                password=password or None,
                start_tls=True,
            )
            return
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Email send failed (html=%s, host=%s) to %s: %s", with_html, host, to, exc
            )
    assert last_exc is not None
    raise last_exc


async def send_email(to: str, subject: str, text_body: str, html_body: str) -> None:
    """Send an email, or log it to stdout when EMAIL_BACKEND=console (dev default).

    Tries the primary SMTP transport, then the fallback one if configured — so
    when the primary (e.g. a free provider that hit its daily limit, or is down)
    fails, delivery falls back to the secondary mailbox instead of dropping.
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

    transports = [
        (
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_username,
            settings.smtp_password,
            settings.smtp_from,
        )
    ]
    if settings.smtp_fallback_configured:
        transports.append(
            (
                settings.smtp_fallback_host,
                settings.smtp_fallback_port,
                settings.smtp_fallback_username,
                settings.smtp_fallback_password,
                settings.smtp_fallback_from or settings.smtp_from,
            )
        )

    last_exc: Exception | None = None
    for host, port, username, password, from_addr in transports:
        try:
            await _send_via(
                to,
                subject,
                text_body,
                html_body,
                host=host,
                port=port,
                username=username,
                password=password,
                from_addr=from_addr,
            )
            return
        except Exception as exc:
            last_exc = exc
            logger.warning("Email transport %s failed to %s; trying next if any", host, to)
    if last_exc is not None:
        raise last_exc


def build_frontend_link(path: str, token: str) -> str:
    return f"{settings.frontend_origin}{path}?token={token}"
