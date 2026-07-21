import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import UserRole
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
async def test_support_list_visible_to_organizer_not_just_admin(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Explicit product requirement: tickets are "видно и админам и
    организаторам" — unlike surveys/CSV-import, which stay admin-only."""
    org = await make_user(session, "org-support1@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-adminsupport1@example.com")
    await session.commit()
    await create_ticket(session, user=runner, body="Need help")
    await session.commit()
    await _login(client, org.id)

    resp = await client.get("/admin-tools/support")
    assert resp.status_code == 200
    assert "Need help" in resp.text


@pytest.mark.asyncio
async def test_reply_blocked_for_anonymous_ticket(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-support2@example.com", UserRole.admin)
    await session.commit()
    ticket = await create_ticket(session, user=None, body="Stuck", guest_name="Ivan")
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

    resp = await client.post(
        f"/admin-tools/support/{ticket.id}/status", follow_redirects=False
    )
    assert resp.status_code == 303
    await session.refresh(ticket)
    assert ticket.status == TicketStatus.closed

    await client.post(f"/admin-tools/support/{ticket.id}/status", follow_redirects=False)
    await session.refresh(ticket)
    assert ticket.status == TicketStatus.open


@pytest.mark.asyncio
async def test_opening_ticket_detail_marks_reporter_messages_read(
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

    after = await client.get("/admin-tools/badge-counts")
    assert after.json()["tickets"] == 0


@pytest.mark.asyncio
async def test_badge_counts_zero_for_anonymous(client: AsyncClient) -> None:
    resp = await client.get("/admin-tools/badge-counts")
    assert resp.status_code == 200
    assert resp.json() == {"tickets": 0, "surveys": 0, "claims": 0, "moderation": 0}
