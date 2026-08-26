import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import StaffPermission, UserRole
from app.models.guest_claim import GuestClaim
from app.models.organizer_permission import OrganizerPermission
from app.services.permissions_service import permissions_for, set_permissions
from tests.factories import make_user


async def _login(client: AsyncClient, user_id: int) -> None:
    token = create_access_token(user_id)
    resp = await client.get(f"/admin-tools/sso?token={token}", follow_redirects=False)
    assert resp.status_code == 302


# --- permissions_service -----------------------------------------------------


@pytest.mark.asyncio
async def test_admin_has_every_permission_with_no_rows(session: AsyncSession) -> None:
    admin = await make_user(session, "admin-perm1@example.com", UserRole.admin)
    await session.commit()

    perms = await permissions_for(session, admin)
    assert perms == set(StaffPermission)
    assert await session.scalar(select(OrganizerPermission)) is None


@pytest.mark.asyncio
async def test_organizer_gets_only_what_was_granted(session: AsyncSession) -> None:
    admin = await make_user(session, "admin-perm2@example.com", UserRole.admin)
    org = await make_user(session, "org-perm2@example.com", UserRole.organizer)
    await session.commit()

    assert await permissions_for(session, org) == set()

    await set_permissions(
        session, org, {StaffPermission.avatars, StaffPermission.surveys}, granted_by=admin
    )
    await session.commit()

    assert await permissions_for(session, org) == {StaffPermission.avatars, StaffPermission.surveys}


@pytest.mark.asyncio
async def test_set_permissions_only_touches_the_diff(session: AsyncSession) -> None:
    admin = await make_user(session, "admin-perm3@example.com", UserRole.admin)
    org = await make_user(session, "org-perm3@example.com", UserRole.organizer)
    await session.commit()

    await set_permissions(
        session, org, {StaffPermission.avatars, StaffPermission.surveys}, granted_by=admin
    )
    await session.commit()
    kept_row_id = await session.scalar(
        select(OrganizerPermission.id).where(
            OrganizerPermission.user_id == org.id,
            OrganizerPermission.permission == StaffPermission.avatars,
        )
    )

    # Drop surveys, add baselines — avatars untouched (same row survives).
    await set_permissions(
        session, org, {StaffPermission.avatars, StaffPermission.baselines}, granted_by=admin
    )
    await session.commit()

    assert await permissions_for(session, org) == {
        StaffPermission.avatars,
        StaffPermission.baselines,
    }
    still_there = await session.scalar(
        select(OrganizerPermission.id).where(
            OrganizerPermission.user_id == org.id,
            OrganizerPermission.permission == StaffPermission.avatars,
        )
    )
    assert still_there == kept_row_id


@pytest.mark.asyncio
async def test_set_permissions_rejects_non_organizer_target(session: AsyncSession) -> None:
    admin = await make_user(session, "admin-perm4@example.com", UserRole.admin)
    runner = await make_user(session, "runner-perm4@example.com")
    await session.commit()

    with pytest.raises(ValueError):
        await set_permissions(session, runner, {StaffPermission.avatars}, granted_by=admin)


# --- /admin-tools/permissions --------------------------------------------------


@pytest.mark.asyncio
async def test_permissions_page_forbidden_for_organizer_and_anonymous(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-perm5@example.com", UserRole.organizer)
    await session.commit()
    await _login(client, org.id)

    resp = await client.get("/admin-tools/permissions", follow_redirects=False)
    assert resp.status_code == 302  # bounced to login, same as any other admin-only page

    client.cookies.clear()  # drop the org's session — now a fully anonymous request
    resp2 = await client.get("/admin-tools/permissions", follow_redirects=False)
    assert resp2.status_code == 302


@pytest.mark.asyncio
async def test_admin_can_grant_and_revoke_via_the_page(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-perm6@example.com", UserRole.admin)
    org = await make_user(session, "org-perm6@example.com", UserRole.organizer)
    await session.commit()
    await _login(client, admin.id)

    listing = await client.get("/admin-tools/permissions")
    assert listing.status_code == 200
    assert org.email in listing.text

    grant = await client.post(
        f"/admin-tools/permissions/{org.id}",
        data={"permissions": ["avatars", "results_review"]},
        follow_redirects=False,
    )
    assert grant.status_code == 303
    # permissions_for issues its own fresh query for the grant rows; org's own
    # columns (role) never change here, so no need to refresh org itself.
    assert await permissions_for(session, org) == {
        StaffPermission.avatars,
        StaffPermission.results_review,
    }

    revoke = await client.post(
        f"/admin-tools/permissions/{org.id}",
        data={"permissions": ["avatars"]},
        follow_redirects=False,
    )
    assert revoke.status_code == 303
    assert await permissions_for(session, org) == {StaffPermission.avatars}


@pytest.mark.asyncio
async def test_granting_to_a_non_organizer_is_rejected(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-perm7@example.com", UserRole.admin)
    runner = await make_user(session, "runner-perm7@example.com")
    await session.commit()
    await _login(client, admin.id)

    resp = await client.post(
        f"/admin-tools/permissions/{runner.id}",
        data={"permissions": ["avatars"]},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "flash_error" in resp.headers["location"]
    assert await session.scalar(select(OrganizerPermission)) is None


# --- representative before/after coverage on the refactored pages -------------


@pytest.mark.asyncio
async def test_avatars_page_opens_once_granted(session: AsyncSession, client: AsyncClient) -> None:
    """Pattern B (tools_avatars.py): was a hard role==admin check, now
    delegable via StaffPermission.avatars."""
    admin = await make_user(session, "admin-perm8@example.com", UserRole.admin)
    org = await make_user(session, "org-perm8@example.com", UserRole.organizer)
    await session.commit()
    await _login(client, org.id)

    before = await client.get("/admin-tools/avatars", follow_redirects=False)
    assert before.status_code == 303  # not granted yet — bounced to dashboard

    await set_permissions(session, org, {StaffPermission.avatars}, granted_by=admin)
    await session.commit()

    after = await client.get("/admin-tools/avatars", follow_redirects=False)
    assert after.status_code == 200


@pytest.mark.asyncio
async def test_csv_import_page_opens_once_granted(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Pattern A (moderation.py): was a hard role==admin check, now delegable
    via StaffPermission.csv_import."""
    admin = await make_user(session, "admin-perm9@example.com", UserRole.admin)
    org = await make_user(session, "org-perm9@example.com", UserRole.organizer)
    await session.commit()
    await _login(client, org.id)

    before = await client.get("/admin-tools/import", follow_redirects=False)
    assert before.status_code == 302  # not granted yet — bounced to login (unchanged UX)

    await set_permissions(session, org, {StaffPermission.csv_import}, granted_by=admin)
    await session.commit()

    after = await client.get("/admin-tools/import", follow_redirects=False)
    assert after.status_code == 200


# --- badge/count endpoints now respect grants ----------------------------------


@pytest.mark.asyncio
async def test_attention_counts_reflect_a_granted_permission(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-perm10@example.com", UserRole.admin)
    org = await make_user(session, "org-perm10@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-perm10@example.com")
    await session.commit()
    session.add(GuestClaim(guest_user_id=runner.id, claimant_user_id=admin.id))
    await set_permissions(session, org, {StaffPermission.guest_claims}, granted_by=admin)
    await session.commit()

    token = create_access_token(org.id)
    resp = await client.get(
        "/api/v1/staff/attention-counts", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["claims"] == 1
