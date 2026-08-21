import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import VERIFY, create_email_token
from app.models.profile_edit_request import ProfileEditRequest
from app.models.user import User
from app.services import rate_guard


def _enable_captcha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "altcha_hmac_key", "test-altcha-secret")


REGISTER = {
    "first_name": "Нина",
    "last_name": "Кова",
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

    users = list(await session.scalars(select(User).where(User.email == REGISTER["email"])))
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
@pytest.mark.parametrize(
    "field,value",
    [
        ("first_name", "Иван2"),  # digit in name
        ("last_name", "Петров9"),
        ("first_name", "Ivan"),  # Latin letters
        ("last_name", "Petrov"),
        ("password", "supersecret"),  # no digit
        ("password", "12345678"),  # no letter
        ("password", "парольпароль1"),  # Cyrillic
        ("password", "short1"),  # < 8 chars
    ],
)
async def test_registration_rejects_invalid_fields(
    client: AsyncClient, field: str, value: str
) -> None:
    payload = {**REGISTER, field: value}
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_registration_capitalizes_names(client: AsyncClient, session: AsyncSession) -> None:
    """The submitted name is post-moderated (see ProfileEditRequest) — it
    lands capitalised in the pending request, not directly on the account,
    which still shows the bootstrap placeholder until an admin approves it."""
    payload = {**REGISTER, "first_name": "  анна", "last_name": "смирнова"}
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 201, r.text

    user = await session.scalar(select(User).where(User.email == REGISTER["email"]))
    assert user is not None
    request = await session.scalar(
        select(ProfileEditRequest).where(ProfileEditRequest.user_id == user.id)
    )
    assert request is not None
    assert request.changes["first_name"] == "Анна"
    assert request.changes["last_name"] == "Смирнова"


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
    assert r.json() == {"enabled": False}

    _enable_captcha(monkeypatch)
    r = await client.get("/api/v1/auth/captcha-config")
    assert r.json() == {"enabled": True}


@pytest.mark.asyncio
async def test_altcha_challenge_solution_roundtrip(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import base64
    import hashlib
    import json

    from app.services import captcha_service

    captcha_service.clear_used()
    _enable_captcha(monkeypatch)

    ch = (await client.get("/api/v1/auth/altcha-challenge")).json()
    number = next(
        n
        for n in range(ch["maxnumber"] + 1)
        if hashlib.sha256(f"{ch['salt']}{n}".encode()).hexdigest() == ch["challenge"]
    )
    payload = base64.b64encode(
        json.dumps(
            {
                "algorithm": ch["algorithm"],
                "challenge": ch["challenge"],
                "number": number,
                "salt": ch["salt"],
                "signature": ch["signature"],
            }
        ).encode()
    ).decode()

    assert await captcha_service.verify_captcha(payload, None) is True
    # A solved challenge can't be replayed.
    assert await captcha_service.verify_captcha(payload, None) is False
    # A forged signature is rejected.
    captcha_service.clear_used()
    tampered = json.loads(base64.b64decode(payload))
    tampered["signature"] = "0" * 64
    bad = base64.b64encode(json.dumps(tampered).encode()).decode()
    assert await captcha_service.verify_captcha(bad, None) is False


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
