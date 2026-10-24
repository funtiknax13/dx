import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import StaffPermission, UserRole
from app.services.permissions_service import set_permissions
from tests.factories import make_baseline, make_user


async def _login(client: AsyncClient, user_id: int) -> None:
    token = create_access_token(user_id)
    resp = await client.get(f"/admin-tools/sso?token={token}", follow_redirects=False)
    assert resp.status_code == 302


@pytest.mark.asyncio
async def test_milestones_page_redirects_to_login_when_anonymous(client: AsyncClient) -> None:
    resp = await client.get("/admin-tools/milestones", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/admin-tools/login"


@pytest.mark.asyncio
async def test_milestones_page_forbidden_for_organizer_without_the_grant(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-ms-admintools1@example.com", UserRole.organizer)
    await session.commit()
    await _login(client, org.id)

    resp = await client.get("/admin-tools/milestones", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/admin-tools/login"


@pytest.mark.asyncio
async def test_milestones_page_lists_runners_bucketed_by_remaining(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-ms-admintools1@example.com", UserRole.admin)
    one_away = await make_user(session, "one-away-admintools1@example.com")
    two_away = await make_user(session, "two-away-admintools1@example.com")
    at_it = await make_user(session, "at-it-admintools1@example.com")
    await make_baseline(session, one_away, dx_count=24)
    await make_baseline(session, two_away, dx_count=23)
    await make_baseline(session, at_it, dx_count=25)
    await session.commit()
    await _login(client, admin.id)

    resp = await client.get("/admin-tools/milestones")
    assert resp.status_code == 200
    assert f"{one_away.first_name} {one_away.last_name}" in resp.text
    assert f"{two_away.first_name} {two_away.last_name}" in resp.text
    assert f"{at_it.first_name} {at_it.last_name}" in resp.text


@pytest.mark.asyncio
async def test_organizer_with_grant_can_see_the_page(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-ms-admintools2@example.com", UserRole.admin)
    org = await make_user(session, "org-ms-admintools2@example.com", UserRole.organizer)
    await set_permissions(session, org, {StaffPermission.milestones}, granted_by=admin)
    await session.commit()
    await _login(client, org.id)

    resp = await client.get("/admin-tools/milestones")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_badge_counts_milestones_needs_the_grant(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-ms-admintools3@example.com", UserRole.admin)
    org = await make_user(session, "org-ms-admintools3@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-ms-admintools3@example.com")
    await make_baseline(session, runner, dx_count=24)  # exactly 1 away from 25
    await session.commit()
    await _login(client, org.id)

    before = await client.get("/admin-tools/badge-counts")
    assert before.json()["milestones"] == 0

    await set_permissions(session, org, {StaffPermission.milestones}, granted_by=admin)
    await session.commit()
    after = await client.get("/admin-tools/badge-counts")
    assert after.json()["milestones"] == 1
