import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import VERIFY, create_email_token
from app.models.user import User

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
async def test_duplicate_registration_conflicts(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=REGISTER)
    r = await client.post("/api/v1/auth/register", json=REGISTER)
    assert r.status_code == 409


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
