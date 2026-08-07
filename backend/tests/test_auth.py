import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import VERIFY, create_email_token
from app.models.user import User
from app.services import rate_guard


def _enable_captcha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "smartcaptcha_client_key", "test-client-key")
    monkeypatch.setattr(settings, "smartcaptcha_server_key", "test-server-key")

REGISTER = {
    "first_name": "Nina",
    "last_name": "Kova",
    "email": "nina@example.com",
    "password": "supersecret1",
    "accept_privacy_policy": True,
}


@pytest.mark.asyncio
async def test_full_auth_flow(client: AsyncClient) -> None:
    # Register
    r = await client.post("/api/v1/auth/register", json=REGISTER)
    assert r.status_code == 201, r.text

    # Login before verification is blocked
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": REGISTER["email"], "password": REGISTER["password"]},
    )
    assert r.status_code == 403

    # Verify email (token normally emailed; synthesize it here)
    token = create_email_token(REGISTER["email"], VERIFY)
    r = await client.get("/api/v1/auth/verify-email", params={"token": token})
    assert r.status_code == 200, r.text

    # Login succeeds
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": REGISTER["email"], "password": REGISTER["password"]},
    )
    assert r.status_code == 200, r.text
    tokens = r.json()
    access = tokens["access_token"]
    refresh = tokens["refresh_token"]

    # Authenticated /me
    r = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    assert r.json()["email"] == REGISTER["email"]
    assert r.json()["role"] == "runner"

    # Refresh yields a new access token
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_duplicate_registration_does_not_leak_existing_email(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Re-registering an existing address must not reveal it's taken (email
    enumeration): same generic 201, and no duplicate account is created."""
    await client.post("/api/v1/auth/register", json=REGISTER)
    r = await client.post("/api/v1/auth/register", json=REGISTER)
    assert r.status_code == 201, r.text

    users = list(
        await session.scalars(select(User).where(User.email == REGISTER["email"]))
    )
    assert len(users) == 1


@pytest.mark.asyncio
async def test_registration_rolls_back_when_email_fails(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the verification email can't be sent (e.g. SMTP down), no account is
    left behind — otherwise it'd be unverifiable *and* block a clean retry
    with a 409."""

    async def failing_send_email(*args: object, **kwargs: object) -> None:
        raise RuntimeError("smtp down")

    monkeypatch.setattr("app.api.auth.send_email", failing_send_email)

    r = await client.post("/api/v1/auth/register", json=REGISTER)
    assert r.status_code == 503

    user = await session.scalar(select(User).where(User.email == REGISTER["email"]))
    assert user is None  # rolled back, not orphaned

    # And once email works again, the same address registers cleanly (no 409).
    monkeypatch.undo()
    retry = await client.post("/api/v1/auth/register", json=REGISTER)
    assert retry.status_code == 201, retry.text


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=REGISTER)
    token = create_email_token(REGISTER["email"], VERIFY)
    await client.get("/api/v1/auth/verify-email", params={"token": token})
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": REGISTER["email"], "password": "wrongpass99"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/users/me")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_registration_requires_privacy_policy_consent(client: AsyncClient) -> None:
    payload = {**REGISTER, "accept_privacy_policy": False}
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_registration_records_consent_timestamp(
    client: AsyncClient, session: AsyncSession
) -> None:
    r = await client.post("/api/v1/auth/register", json=REGISTER)
    assert r.status_code == 201, r.text

    user = await session.scalar(select(User).where(User.email == REGISTER["email"]))
    assert user is not None
    assert user.privacy_accepted_at is not None


@pytest.mark.asyncio
async def test_captcha_config_reflects_settings(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = await client.get("/api/v1/auth/captcha-config")
    assert r.status_code == 200
    assert r.json() == {"enabled": False, "client_key": None}

    _enable_captcha(monkeypatch)
    r = await client.get("/api/v1/auth/captcha-config")
    assert r.json() == {"enabled": True, "client_key": "test-client-key"}


@pytest.mark.asyncio
async def test_login_gate_requires_captcha_after_repeated_failures(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    rate_guard.clear_all()
    _enable_captcha(monkeypatch)
    monkeypatch.setattr(settings, "captcha_login_threshold", 3)

    await client.post("/api/v1/auth/register", json=REGISTER)
    token = create_email_token(REGISTER["email"], VERIFY)
    await client.get("/api/v1/auth/verify-email", params={"token": token})

    bad = {"email": REGISTER["email"], "password": "wrongpass99"}
    for _ in range(3):
        assert (await client.post("/api/v1/auth/login", json=bad)).status_code == 401

    # Threshold reached: a token is now demanded before the attempt is judged.
    assert (await client.post("/api/v1/auth/login", json=bad)).status_code == 428

    # A valid token clears the gate — back to a normal 401 for the wrong password.
    async def _ok(*_a: object, **_k: object) -> bool:
        return True

    monkeypatch.setattr("app.api.auth.verify_captcha", _ok)
    r = await client.post("/api/v1/auth/login", json={**bad, "captcha_token": "solved"})
    assert r.status_code == 401
    rate_guard.clear_all()


@pytest.mark.asyncio
async def test_anonymous_support_requires_captcha_when_enabled(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_captcha(monkeypatch)
    body = {"body": "Нужна помощь", "guest_name": "Гость"}

    # No token from an anonymous reporter → gated.
    assert (await client.post("/api/v1/support/tickets", json=body)).status_code == 428

    async def _ok(*_a: object, **_k: object) -> bool:
        return True

    monkeypatch.setattr("app.api.support.verify_captcha", _ok)
    r = await client.post("/api/v1/support/tickets", json={**body, "captcha_token": "solved"})
    assert r.status_code == 201, r.text
