import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import StaffPermission, UserRole
from app.models.guest_claim import GuestClaim
from app.models.organizer_permission import OrganizerPermission
from app.services.permissions_service import permissions_for, set_permissions
from tests.factories import make_event_group, make_user


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


# --- role assignment on /admin-tools/permissions -------------------------------


@pytest.mark.asyncio
async def test_promote_makes_a_found_runner_an_organizer_with_no_grants(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-perm11@example.com", UserRole.admin)
    runner = await make_user(session, "runner-perm11@example.com")
    await session.commit()
    await _login(client, admin.id)

    search = await client.get("/admin-tools/permissions", params={"q": "runner-perm11"})
    assert search.status_code == 200
    assert runner.email in search.text

    resp = await client.post(
        f"/admin-tools/permissions/{runner.id}/promote", follow_redirects=False
    )
    assert resp.status_code == 303

    await session.refresh(runner)
    assert runner.role == UserRole.organizer
    assert await permissions_for(session, runner) == set()


@pytest.mark.asyncio
async def test_promote_rejects_a_non_runner_target(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-perm12@example.com", UserRole.admin)
    other_admin = await make_user(session, "admin-perm13@example.com", UserRole.admin)
    already_org = await make_user(session, "org-perm12@example.com", UserRole.organizer)
    await session.commit()
    await _login(client, admin.id)

    for target in (other_admin, already_org):
        original_role = target.role
        resp = await client.post(
            f"/admin-tools/permissions/{target.id}/promote", follow_redirects=False
        )
        assert resp.status_code == 303
        assert "flash_error" in resp.headers["location"]
        await session.refresh(target)
        assert target.role == original_role  # unchanged


@pytest.mark.asyncio
async def test_demote_clears_role_and_every_grant(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-perm14@example.com", UserRole.admin)
    org = await make_user(session, "org-perm14@example.com", UserRole.organizer)
    await session.commit()
    await set_permissions(
        session, org, {StaffPermission.avatars, StaffPermission.events}, granted_by=admin
    )
    await session.commit()
    await _login(client, admin.id)

    resp = await client.post(f"/admin-tools/permissions/{org.id}/demote", follow_redirects=False)
    assert resp.status_code == 303

    await session.refresh(org)
    assert org.role == UserRole.runner
    assert (
        await session.scalar(
            select(OrganizerPermission).where(OrganizerPermission.user_id == org.id)
        )
        is None
    )


@pytest.mark.asyncio
async def test_demote_rejects_a_non_organizer_target(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-perm15@example.com", UserRole.admin)
    runner = await make_user(session, "runner-perm15@example.com")
    await session.commit()
    await _login(client, admin.id)

    resp = await client.post(f"/admin-tools/permissions/{runner.id}/demote", follow_redirects=False)
    assert resp.status_code == 303
    assert "flash_error" in resp.headers["location"]


# --- events/support permissions -------------------------------------------------


@pytest.mark.asyncio
async def test_events_permission_gates_admin_tools_event_creation(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-perm16@example.com", UserRole.admin)
    org = await make_user(session, "org-perm16@example.com", UserRole.organizer)
    event, _ = await make_event_group(session, org)
    await session.commit()
    await _login(client, org.id)

    before = await client.get(f"/admin-tools/events/{event.id}/edit", follow_redirects=False)
    assert before.status_code == 302  # not granted yet — bounced to login (Pattern A)

    await set_permissions(session, org, {StaffPermission.events}, granted_by=admin)
    await session.commit()

    after = await client.get(f"/admin-tools/events/{event.id}/edit", follow_redirects=False)
    assert after.status_code == 200


@pytest.mark.asyncio
async def test_events_permission_gates_the_rest_api(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-perm17@example.com", UserRole.admin)
    org = await make_user(session, "org-perm17@example.com", UserRole.organizer)
    await session.commit()
    token = create_access_token(org.id)

    payload = {"title": "DX Test", "date": "2026-09-01", "description": ""}
    before = await client.post(
        "/api/v1/events", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert before.status_code == 403

    await set_permissions(session, org, {StaffPermission.events}, granted_by=admin)
    await session.commit()

    after = await client.post(
        "/api/v1/events", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert after.status_code == 201, after.text


@pytest.mark.asyncio
async def test_support_permission_gates_the_ticket_list(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-perm18@example.com", UserRole.admin)
    org = await make_user(session, "org-perm18@example.com", UserRole.organizer)
    await session.commit()
    await _login(client, org.id)

    before = await client.get("/admin-tools/support", follow_redirects=False)
    assert before.status_code == 302

    await set_permissions(session, org, {StaffPermission.support}, granted_by=admin)
    await session.commit()

    after = await client.get("/admin-tools/support", follow_redirects=False)
    assert after.status_code == 200
