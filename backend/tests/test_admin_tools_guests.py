import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.enums import UserRole
from app.models.user import User
from tests.factories import make_user


async def _login(client: AsyncClient, user_id: int) -> None:
    token = create_access_token(user_id)
    resp = await client.get(f"/admin-tools/sso?token={token}", follow_redirects=False)
    assert resp.status_code == 302


async def _make_guest(session: AsyncSession, email: str, first: str, last: str) -> User:
    guest = User(
        first_name=first,
        last_name=last,
        email=email,
        password_hash=hash_password("unusable"),
        email_verified=True,
        role=UserRole.runner,
        is_guest=True,
    )
    session.add(guest)
    await session.flush()
    return guest


@pytest.mark.asyncio
async def test_rename_guest_updates_name(session: AsyncSession, client: AsyncClient) -> None:
    admin = await make_user(session, "admin-guests1@example.com", UserRole.admin)
    guest = await _make_guest(session, "guest1@dh.local", "иван", "иванов")
    await session.commit()
    await _login(client, admin.id)

    resp = await client.post(
        f"/admin-tools/guests/{guest.id}/rename",
        data={"first_name": "Иван", "last_name": "Иванов"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "flash=" in resp.headers["location"]

    await session.refresh(guest)
    assert guest.first_name == "Иван"
    assert guest.last_name == "Иванов"


@pytest.mark.asyncio
async def test_rename_guest_rejects_blank_name(session: AsyncSession, client: AsyncClient) -> None:
    admin = await make_user(session, "admin-guests2@example.com", UserRole.admin)
    guest = await _make_guest(session, "guest2@dh.local", "Мария", "Тестова")
    await session.commit()
    await _login(client, admin.id)

    resp = await client.post(
        f"/admin-tools/guests/{guest.id}/rename",
        data={"first_name": "  ", "last_name": "Тестова"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "flash_error=" in resp.headers["location"]

    await session.refresh(guest)
    assert guest.first_name == "Мария"


@pytest.mark.asyncio
async def test_rename_guest_rejects_a_non_guest_target(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-guests3@example.com", UserRole.admin)
    real_user = await make_user(session, "real-guests3@example.com")
    await session.commit()
    await _login(client, admin.id)

    resp = await client.post(
        f"/admin-tools/guests/{real_user.id}/rename",
        data={"first_name": "Hacked", "last_name": "Name"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "flash_error=" in resp.headers["location"]

    await session.refresh(real_user)
    assert real_user.first_name != "Hacked"


@pytest.mark.asyncio
async def test_rename_guest_requires_guest_claims_permission(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-guests4@example.com", UserRole.organizer)
    guest = await _make_guest(session, "guest4@dh.local", "Олег", "Тестовый")
    await session.commit()
    await _login(client, org.id)

    resp = await client.post(
        f"/admin-tools/guests/{guest.id}/rename",
        data={"first_name": "Should", "last_name": "NotApply"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/admin-tools/login"

    await session.refresh(guest)
    assert guest.first_name == "Олег"
