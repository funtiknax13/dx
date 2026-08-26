import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import StaffPermission, UserRole
from app.services.permissions_service import set_permissions
from tests.factories import make_user


async def _login(client: AsyncClient, user_id: int) -> None:
    token = create_access_token(user_id)
    resp = await client.get(f"/admin-tools/sso?token={token}", follow_redirects=False)
    assert resp.status_code == 302


@pytest.mark.asyncio
async def test_runners_page_redirects_to_login_when_anonymous(client: AsyncClient) -> None:
    resp = await client.get("/admin-tools/runners", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/admin-tools/login"


@pytest.mark.asyncio
async def test_runners_page_forbidden_for_organizer_even_with_every_other_permission(
    session: AsyncSession, client: AsyncClient
) -> None:
    """The one page in admin-tools that stays a hard admin check no matter
    what — full profile data (everything but the password hash) is more
    sensitive than any single delegable StaffPermission."""
    admin = await make_user(session, "admin-runnerspage@example.com", UserRole.admin)
    org = await make_user(session, "org-runnerspage@example.com", UserRole.organizer)
    await session.commit()
    await set_permissions(session, org, set(StaffPermission), granted_by=admin)
    await session.commit()
    await _login(client, org.id)

    resp = await client.get("/admin-tools/runners", follow_redirects=False)
    assert resp.status_code == 302

    detail = await client.get(f"/admin-tools/runners/{admin.id}", follow_redirects=False)
    assert detail.status_code == 302


@pytest.mark.asyncio
async def test_runners_list_excludes_guests(session: AsyncSession, client: AsyncClient) -> None:
    admin = await make_user(session, "admin-runners1@example.com", UserRole.admin)
    real = await make_user(session, "real-runners1@example.com")
    real.first_name = "Настоящий"
    real.last_name = "Бегун"
    guest = await make_user(session, "guest-runners1@example.com")
    guest.is_guest = True
    guest.first_name = "Гостевой"
    guest.last_name = "Профиль"
    await session.commit()
    await _login(client, admin.id)

    resp = await client.get("/admin-tools/runners")
    assert resp.status_code == 200
    assert "Настоящий Бегун" in resp.text
    assert "Гостевой Профиль" not in resp.text


@pytest.mark.asyncio
async def test_runners_search_filters_by_name(session: AsyncSession, client: AsyncClient) -> None:
    admin = await make_user(session, "admin-runners2@example.com", UserRole.admin)
    match = await make_user(session, "runner-zebrovsky@example.com")
    match.first_name = "Захар"
    match.last_name = "Зебровский"
    other = await make_user(session, "runner-other@example.com")
    other.first_name = "Иван"
    other.last_name = "Иванов"
    await session.commit()
    await _login(client, admin.id)

    resp = await client.get("/admin-tools/runners", params={"q": "Зебровский"})
    assert resp.status_code == 200
    assert "Захар Зебровский" in resp.text
    assert "Иван Иванов" not in resp.text


@pytest.mark.asyncio
async def test_runners_pagination_shows_25_per_page(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-runners3@example.com", UserRole.admin)
    for i in range(30):
        await make_user(session, f"runner-page{i}@example.com")
    await session.commit()
    await _login(client, admin.id)

    page1 = await client.get("/admin-tools/runners")
    assert page1.status_code == 200
    # One per-row detail link per data row — unambiguous count (the shared
    # `[data-modal-url]` JS selector in _base.html would also match a bare
    # substring count of "data-modal-url" itself, since that string appears
    # literally inside the <script> block too).
    assert page1.text.count('<a href="/admin-tools/runners/') == 25
    assert "Страница 1 из 2" in page1.text

    page2 = await client.get("/admin-tools/runners", params={"page": 2})
    assert page2.status_code == 200
    assert "Страница 2 из 2" in page2.text


@pytest.mark.asyncio
async def test_runner_detail_shows_full_profile(session: AsyncSession, client: AsyncClient) -> None:
    admin = await make_user(session, "admin-runners4@example.com", UserRole.admin)
    runner = await make_user(session, "runner-detail@example.com")
    await session.commit()
    await _login(client, admin.id)

    resp = await client.get(f"/admin-tools/runners/{runner.id}")
    assert resp.status_code == 200
    assert runner.email in resp.text
    assert "Чебоксары" in resp.text  # city, from make_user's complete_profile default
    assert "+79990000000" in resp.text  # phone
    assert "Женский" in resp.text  # gender
    assert "01.01.1990" in resp.text  # birthday


@pytest.mark.asyncio
async def test_runner_detail_redirects_for_a_guest_target(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-runners5@example.com", UserRole.admin)
    guest = await make_user(session, "guest-runners5@example.com")
    guest.is_guest = True
    await session.commit()
    await _login(client, admin.id)

    resp = await client.get(f"/admin-tools/runners/{guest.id}", follow_redirects=False)
    assert resp.status_code == 303
