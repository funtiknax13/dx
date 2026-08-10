import pytest

from app.core import email as email_mod
from app.core.config import settings


@pytest.mark.asyncio
async def test_send_email_falls_back_when_primary_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "primary.example")
    monkeypatch.setattr(settings, "smtp_from", "Primary <p@primary.example>")
    monkeypatch.setattr(settings, "smtp_fallback_host", "fallback.example")
    monkeypatch.setattr(settings, "smtp_fallback_from", "Fallback <f@fallback.example>")

    attempts: list[str] = []

    async def fake_send(message: object, *, hostname: str, **kwargs: object) -> None:
        attempts.append(hostname)
        if hostname == "primary.example":
            raise RuntimeError("primary hit its limit")

    monkeypatch.setattr("app.core.email.aiosmtplib.send", fake_send)

    await email_mod.send_email("runner@gmail.com", "Subj", "text", "<p>html</p>")

    assert "primary.example" in attempts  # primary attempted first
    assert attempts[-1] == "fallback.example"  # and delivery fell back


@pytest.mark.asyncio
async def test_send_email_raises_when_primary_fails_and_no_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "email_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "primary.example")
    monkeypatch.setattr(settings, "smtp_fallback_host", "")

    async def fake_send(message: object, *, hostname: str, **kwargs: object) -> None:
        raise RuntimeError("down")

    monkeypatch.setattr("app.core.email.aiosmtplib.send", fake_send)

    with pytest.raises(RuntimeError):
        await email_mod.send_email("runner@gmail.com", "Subj", "text", "<p>html</p>")
