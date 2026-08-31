import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.enums import UserRole
from app.models.user import User
from app.services.guest_service import merge_guest_into
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


@pytest.mark.asyncio
async def test_guests_list_search_filters_by_name(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-guests5@example.com", UserRole.admin)
    await _make_guest(session, "guest5a@dh.local", "Пётр", "Смирнов")
    await _make_guest(session, "guest5b@dh.local", "Анна", "Кузнецова")
    await session.commit()
    await _login(client, admin.id)

    resp = await client.get("/admin-tools/guests", params={"q": "Смирнов"})
    assert resp.status_code == 200
    assert "Смирнов" in resp.text
    assert "Кузнецова" not in resp.text


@pytest.mark.asyncio
async def test_guests_list_excludes_merged_guests(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-guests6@example.com", UserRole.admin)
    real_user = await make_user(session, "real-guests6@example.com")
    guest = await _make_guest(session, "guest6@dh.local", "Слился", "Гость")
    await session.commit()
    await merge_guest_into(session, guest, real_user)
    await session.commit()
    await _login(client, admin.id)

    resp = await client.get("/admin-tools/guests")
    assert resp.status_code == 200
    assert "Слился" not in resp.text


@pytest.mark.asyncio
async def test_guest_detail_partial_returns_bare_fragment(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-guests7@example.com", UserRole.admin)
    guest = await _make_guest(session, "guest7@dh.local", "Фрагмент", "Тестовый")
    await session.commit()
    await _login(client, admin.id)

    resp = await client.get(f"/admin-tools/guests/{guest.id}", params={"partial": "1"})
    assert resp.status_code == 200
    assert "Фрагмент" in resp.text
    assert "<nav" not in resp.text  # no sidebar chrome in the fragment


@pytest.mark.asyncio
async def test_guest_detail_full_page_includes_nav(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-guests8@example.com", UserRole.admin)
    guest = await _make_guest(session, "guest8@dh.local", "Полная", "Страница")
    await session.commit()
    await _login(client, admin.id)

    resp = await client.get(f"/admin-tools/guests/{guest.id}")
    assert resp.status_code == 200
    assert "Полная" in resp.text
    assert "<nav" in resp.text


@pytest.mark.asyncio
async def test_guest_detail_search_finds_merge_candidate(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-guests9@example.com", UserRole.admin)
    real_user = await make_user(session, "real-guests9@example.com")
    real_user.first_name = "Findme"
    guest = await _make_guest(session, "guest9@dh.local", "Ищу", "Совпадение")
    await session.commit()
    await _login(client, admin.id)

    resp = await client.get(f"/admin-tools/guests/{guest.id}", params={"q": "Findme"})
    assert resp.status_code == 200
    assert real_user.email in resp.text


@pytest.mark.asyncio
async def test_guest_detail_excludes_a_merged_guest(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-guests10@example.com", UserRole.admin)
    real_user = await make_user(session, "real-guests10@example.com")
    guest = await _make_guest(session, "guest10@dh.local", "Уже", "Слился")
    await session.commit()
    await merge_guest_into(session, guest, real_user)
    await session.commit()
    await _login(client, admin.id)

    full = await client.get(f"/admin-tools/guests/{guest.id}", follow_redirects=False)
    assert full.status_code == 303
    assert full.headers["location"] == "/admin-tools/guests"

    partial = await client.get(f"/admin-tools/guests/{guest.id}", params={"partial": "1"})
    assert partial.status_code == 404
