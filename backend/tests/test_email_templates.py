import pytest

from app.core.email import render_email_html, send_email


def test_verify_email_renders_link_and_name() -> None:
    html = render_email_html(
        "verify_email.html", first_name="Иван", link="https://example.com/verify?token=abc"
    )
    assert "Иван" in html
    assert "https://example.com/verify?token=abc" in html
    assert "<!doctype html>" in html.lower()


def test_reset_password_renders_link() -> None:
    html = render_email_html("reset_password.html", link="https://example.com/reset?token=abc")
    assert "https://example.com/reset?token=abc" in html
    assert "2 часа" in html


def test_support_reply_escapes_html_in_reply_body() -> None:
    """The reply body is staff-authored free text, not trusted markup — a
    stray '<' shouldn't be able to inject tags into the email."""
    html = render_email_html(
        "support_reply.html",
        first_name="Мария",
        reply_body="Смотрите <script>alert(1)</script> и распишитесь",
        link="https://example.com/support/tickets/1",
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_support_reply_converts_newlines_to_br() -> None:
    html = render_email_html(
        "support_reply.html",
        first_name="Мария",
        reply_body="Первая строка\nВторая строка",
        link="https://example.com/support/tickets/1",
    )
    assert "Первая строка<br>" in html
    assert "Вторая строка" in html


@pytest.mark.asyncio
async def test_send_email_console_backend_logs_text_body(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO", logger="app.email"):
        await send_email("runner@example.com", "Тема письма", "Текстовая версия", "<p>HTML</p>")
    assert "Тема письма" in caplog.text
    assert "Текстовая версия" in caplog.text
