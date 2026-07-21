import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import UserRole
from app.services.support_service import add_message, create_ticket
from tests.factories import make_user


@pytest.mark.asyncio
async def test_create_ticket_anonymous_requires_guest_name(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/support/tickets", json={"body": "Help"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_ticket_anonymous_with_guest_name_succeeds(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/support/tickets",
        json={"body": "Stuck registering", "guest_name": "Ivan"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "open"
    assert body["has_unread"] is False


@pytest.mark.asyncio
async def test_create_ticket_authenticated_links_to_user(
    session: AsyncSession, client: AsyncClient
) -> None:
    runner = await make_user(session, "runner-supportapi1@example.com")
    await session.commit()
    token = create_access_token(runner.id)

    resp = await client.post(
        "/api/v1/support/tickets",
        headers={"Authorization": f"Bearer {token}"},
        json={"body": "Question about signup"},
    )
    assert resp.status_code == 201, resp.text

    mine = await client.get(
        "/api/v1/support/tickets", headers={"Authorization": f"Bearer {token}"}
    )
    assert mine.status_code == 200
    tickets = mine.json()
    assert len(tickets) == 1
    assert tickets[0]["preview"] == "Question about signup"


@pytest.mark.asyncio
async def test_my_tickets_excludes_other_users_tickets(
    session: AsyncSession, client: AsyncClient
) -> None:
    runner1 = await make_user(session, "runner-supportapi2@example.com")
    runner2 = await make_user(session, "runner-supportapi3@example.com")
    await session.commit()
    await create_ticket(session, user=runner1, body="Runner1's ticket")
    await session.commit()

    token2 = create_access_token(runner2.id)
    resp = await client.get(
        "/api/v1/support/tickets", headers={"Authorization": f"Bearer {token2}"}
    )
    assert resp.json() == []


@pytest.mark.asyncio
async def test_ticket_detail_404_for_non_owner(session: AsyncSession, client: AsyncClient) -> None:
    runner1 = await make_user(session, "runner-supportapi4@example.com")
    runner2 = await make_user(session, "runner-supportapi5@example.com")
    await session.commit()
    ticket = await create_ticket(session, user=runner1, body="Private")
    await session.commit()

    token2 = create_access_token(runner2.id)
    resp = await client.get(
        f"/api/v1/support/tickets/{ticket.id}", headers={"Authorization": f"Bearer {token2}"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ticket_detail_marks_staff_messages_read_and_unread_count_drops(
    session: AsyncSession, client: AsyncClient
) -> None:
    runner = await make_user(session, "runner-supportapi6@example.com")
    admin = await make_user(session, "admin-supportapi6@example.com", UserRole.admin)
    await session.commit()
    ticket = await create_ticket(session, user=runner, body="Question")
    await add_message(session, ticket, sender=admin, is_staff=True, body="Reply")
    await session.commit()

    token = create_access_token(runner.id)
    headers = {"Authorization": f"Bearer {token}"}

    unread_before = await client.get("/api/v1/support/tickets/unread-count", headers=headers)
    assert unread_before.json()["count"] == 1

    detail = await client.get(f"/api/v1/support/tickets/{ticket.id}", headers=headers)
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) == 2

    unread_after = await client.get("/api/v1/support/tickets/unread-count", headers=headers)
    assert unread_after.json()["count"] == 0


@pytest.mark.asyncio
async def test_reporter_reply_reopens_closed_ticket_via_api(
    session: AsyncSession, client: AsyncClient
) -> None:
    from app.models.enums import TicketStatus

    runner = await make_user(session, "runner-supportapi7@example.com")
    await session.commit()
    ticket = await create_ticket(session, user=runner, body="Question")
    ticket.status = TicketStatus.closed
    await session.commit()

    token = create_access_token(runner.id)
    resp = await client.post(
        f"/api/v1/support/tickets/{ticket.id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"body": "One more thing"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "open"
