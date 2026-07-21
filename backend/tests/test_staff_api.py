import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import FinishStatus, ModerationStatus, UserRole
from app.models.guest_claim import GuestClaim
from app.services.support_service import create_ticket
from tests.factories import make_attendance_with_result, make_event_group, make_user


@pytest.mark.asyncio
async def test_attention_counts_zero_for_runner(session: AsyncSession, client: AsyncClient) -> None:
    runner = await make_user(session, "runner-staffapi1@example.com")
    await session.commit()
    token = create_access_token(runner.id)

    resp = await client.get(
        "/api/v1/staff/attention-counts", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"tickets": 0, "claims": 0, "moderation": 0}


@pytest.mark.asyncio
async def test_organizer_sees_only_ticket_count_not_admin_only_queues(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Claims and moderation are Admin-only actions (see CLAUDE.md) — an
    organizer has no admin-tools link for them, so no badge count either."""
    org = await make_user(session, "org-staffapi1@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-staffapi2@example.com")
    admin = await make_user(session, "admin-staffapi1@example.com", UserRole.admin)
    await session.commit()
    await create_ticket(session, user=runner, body="Question")
    await session.commit()
    session.add(GuestClaim(guest_user_id=runner.id, claimant_user_id=admin.id))
    await session.commit()

    token = create_access_token(org.id)
    resp = await client.get(
        "/api/v1/staff/attention-counts", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tickets"] == 1
    assert body["claims"] == 0
    assert body["moderation"] == 0


@pytest.mark.asyncio
async def test_admin_sees_full_breakdown(session: AsyncSession, client: AsyncClient) -> None:
    admin = await make_user(session, "admin-staffapi2@example.com", UserRole.admin)
    runner = await make_user(session, "runner-staffapi3@example.com")
    guest_target = await make_user(session, "runner-staffapi4@example.com")
    org = await make_user(session, "org-staffapi2@example.com", UserRole.organizer)
    _, group = await make_event_group(session, org)
    await session.commit()

    await create_ticket(session, user=runner, body="Question")
    session.add(GuestClaim(guest_user_id=guest_target.id, claimant_user_id=runner.id))
    await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.pending,
    )
    await session.commit()

    token = create_access_token(admin.id)
    resp = await client.get(
        "/api/v1/staff/attention-counts", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"tickets": 1, "claims": 1, "moderation": 1}
