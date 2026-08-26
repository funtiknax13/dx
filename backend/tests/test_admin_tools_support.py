import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import StaffPermission, TicketStatus, UserRole
from app.models.support import SupportMessage, SupportTicket
from app.services.permissions_service import set_permissions
from app.services.support_service import create_ticket
from tests.factories import make_user


async def _login(client: AsyncClient, user_id: int) -> None:
    token = create_access_token(user_id)
    resp = await client.get(f"/admin-tools/sso?token={token}", follow_redirects=False)
    assert resp.status_code == 302


@pytest.mark.asyncio
async def test_support_list_redirects_to_login_when_anonymous(client: AsyncClient) -> None:
    resp = await client.get("/admin-tools/support", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/admin-tools/login"


@pytest.mark.asyncio
async def test_support_list_visible_to_organizer_with_support_granted(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Tickets are delegable like everything else now (StaffPermission
    .support) rather than an unconditional organizer baseline — every
    *existing* organizer got backfilled with it in the introducing
    migration, so in practice this is the common case, but a freshly
    promoted organizer starts without it (see the zero-grant test below)."""
    admin = await make_user(session, "admin-support6@example.com", UserRole.admin)
    org = await make_user(session, "org-support1@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-adminsupport1@example.com")
    await session.commit()
    await create_ticket(session, user=runner, body="Need help")
    await set_permissions(session, org, {StaffPermission.support}, granted_by=admin)
    await session.commit()
    await _login(client, org.id)

    resp = await client.get("/admin-tools/support")
    assert resp.status_code == 200
    assert "Need help" in resp.text


@pytest.mark.asyncio
async def test_support_list_forbidden_for_organizer_without_the_grant(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-support7@example.com", UserRole.organizer)
    await session.commit()
    await _login(client, org.id)

    resp = await client.get("/admin-tools/support", follow_redirects=False)
    assert resp.status_code == 302


@pytest.mark.asyncio
async def test_reply_blocked_for_anonymous_ticket(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-support2@example.com", UserRole.admin)
    await session.commit()
    # Legacy anonymous ticket (support is login-only now, but old/anonymized
    # tickets can still exist) — build it directly, not via the service.
    ticket = SupportTicket(status=TicketStatus.open, created_by_user_id=None, guest_name="Ivan")
    session.add(ticket)
    await session.flush()
    session.add(
        SupportMessage(ticket_id=ticket.id, sender_user_id=None, is_staff=False, body="Stuck")
    )
    await session.commit()
    await _login(client, admin.id)

    resp = await client.post(
        f"/admin-tools/support/{ticket.id}/reply",
        data={"body": "Trying to reply anyway"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "flash_error" in resp.headers["location"]

    await session.refresh(ticket, attribute_names=["messages"])
    assert len(ticket.messages) == 1


@pytest.mark.asyncio
async def test_reply_to_registered_users_ticket_adds_staff_message(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-support3@example.com", UserRole.admin)
    runner = await make_user(session, "runner-adminsupport3@example.com")
    await session.commit()
    ticket = await create_ticket(session, user=runner, body="Question")
    await session.commit()
    await _login(client, admin.id)

    resp = await client.post(
        f"/admin-tools/support/{ticket.id}/reply",
        data={"body": "Here is the answer"},
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text

    await session.refresh(ticket, attribute_names=["messages"])
    assert len(ticket.messages) == 2
    assert ticket.messages[-1].is_staff is True
    assert ticket.messages[-1].body == "Here is the answer"


@pytest.mark.asyncio
async def test_status_toggle_flips_open_and_closed(
    session: AsyncSession, client: AsyncClient
) -> None:
    from app.models.enums import TicketStatus

    admin = await make_user(session, "admin-support4@example.com", UserRole.admin)
    runner = await make_user(session, "runner-adminsupport4@example.com")
    await session.commit()
    ticket = await create_ticket(session, user=runner, body="Question")
    await session.commit()
    await _login(client, admin.id)

    resp = await client.post(f"/admin-tools/support/{ticket.id}/status", follow_redirects=False)
    assert resp.status_code == 303
    await session.refresh(ticket)
    assert ticket.status == TicketStatus.closed

    await client.post(f"/admin-tools/support/{ticket.id}/status", follow_redirects=False)
    await session.refresh(ticket)
    assert ticket.status == TicketStatus.open


@pytest.mark.asyncio
async def test_opening_ticket_detail_does_not_clear_awaiting_reply_badge(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-support5@example.com", UserRole.admin)
    runner = await make_user(session, "runner-adminsupport5@example.com")
    await session.commit()
    ticket = await create_ticket(session, user=runner, body="Question")
    await session.commit()
    await _login(client, admin.id)

    before = await client.get("/admin-tools/badge-counts")
    assert before.json()["tickets"] == 1

    detail = await client.get(f"/admin-tools/support/{ticket.id}")
    assert detail.status_code == 200

    # Merely viewing the ticket must not clear the badge — nobody has
    # replied yet, it's still awaiting a staff reply.
    after = await client.get("/admin-tools/badge-counts")
    assert after.json()["tickets"] == 1

    reply = await client.post(
        f"/admin-tools/support/{ticket.id}/reply",
        data={"body": "Answer"},
        follow_redirects=False,
    )
    assert reply.status_code == 303

    after_reply = await client.get("/admin-tools/badge-counts")
    assert after_reply.json()["tickets"] == 0


@pytest.mark.asyncio
async def test_badge_counts_zero_for_anonymous(client: AsyncClient) -> None:
    resp = await client.get("/admin-tools/badge-counts")
    assert resp.status_code == 200
    assert resp.json() == {
        "tickets": 0,
        "surveys": 0,
        "claims": 0,
        "moderation": 0,
        "avatars": 0,
        "profile_review": 0,
    }
