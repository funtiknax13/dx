import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TicketStatus, UserRole
from app.services.support_service import (
    add_message,
    create_ticket,
    has_unread_for_user,
    mark_read_by_reporter,
    mark_read_by_staff,
    unread_ticket_count_for_staff,
    unread_ticket_count_for_user,
)
from tests.factories import make_user


@pytest.mark.asyncio
async def test_create_ticket_for_logged_in_user(session: AsyncSession) -> None:
    runner = await make_user(session, "runner-support1@example.com")
    await session.commit()

    ticket = await create_ticket(session, user=runner, body="Help please")
    await session.commit()
    await session.refresh(ticket, attribute_names=["messages"])

    assert ticket.status == TicketStatus.open
    assert ticket.created_by_user_id == runner.id
    assert ticket.guest_name is None
    assert len(ticket.messages) == 1
    assert ticket.messages[0].is_staff is False
    assert ticket.messages[0].body == "Help please"


@pytest.mark.asyncio
async def test_create_ticket_anonymous_stores_guest_contact(session: AsyncSession) -> None:
    ticket = await create_ticket(
        session,
        user=None,
        body="Stuck registering",
        guest_name="Ivan",
        guest_contact="ivan@example.com",
    )
    await session.commit()

    assert ticket.created_by_user_id is None
    assert ticket.guest_name == "Ivan"
    assert ticket.guest_contact == "ivan@example.com"


@pytest.mark.asyncio
async def test_reporter_message_reopens_closed_ticket(session: AsyncSession) -> None:
    runner = await make_user(session, "runner-support2@example.com")
    await session.commit()
    ticket = await create_ticket(session, user=runner, body="First message")
    ticket.status = TicketStatus.closed
    await session.commit()

    await add_message(session, ticket, sender=runner, is_staff=False, body="Still broken")
    await session.commit()

    assert ticket.status == TicketStatus.open


@pytest.mark.asyncio
async def test_staff_message_does_not_reopen_closed_ticket(session: AsyncSession) -> None:
    """A staff reply on an already-closed ticket is a closing note, not a
    sign the issue reopened — asymmetric with the reporter-message case."""
    runner = await make_user(session, "runner-support3@example.com")
    admin = await make_user(session, "admin-support3@example.com", UserRole.admin)
    await session.commit()
    ticket = await create_ticket(session, user=runner, body="First message")
    ticket.status = TicketStatus.closed
    await session.commit()

    await add_message(session, ticket, sender=admin, is_staff=True, body="Closing note")
    await session.commit()

    assert ticket.status == TicketStatus.closed


@pytest.mark.asyncio
async def test_mark_read_by_staff_only_clears_reporter_messages(session: AsyncSession) -> None:
    runner = await make_user(session, "runner-support4@example.com")
    admin = await make_user(session, "admin-support4@example.com", UserRole.admin)
    await session.commit()
    ticket = await create_ticket(session, user=runner, body="Question")
    await add_message(session, ticket, sender=admin, is_staff=True, body="Answer")
    await session.commit()

    await mark_read_by_staff(session, ticket)
    await session.commit()
    await session.refresh(ticket, attribute_names=["messages"])

    assert all(m.read_at is not None for m in ticket.messages if not m.is_staff)
    assert all(m.read_at is None for m in ticket.messages if m.is_staff)


@pytest.mark.asyncio
async def test_mark_read_by_reporter_only_clears_staff_messages(session: AsyncSession) -> None:
    runner = await make_user(session, "runner-support5@example.com")
    admin = await make_user(session, "admin-support5@example.com", UserRole.admin)
    await session.commit()
    ticket = await create_ticket(session, user=runner, body="Question")
    await add_message(session, ticket, sender=admin, is_staff=True, body="Answer")
    await session.commit()

    await mark_read_by_reporter(session, ticket)
    await session.commit()
    await session.refresh(ticket, attribute_names=["messages"])

    assert all(m.read_at is not None for m in ticket.messages if m.is_staff)
    assert all(m.read_at is None for m in ticket.messages if not m.is_staff)


@pytest.mark.asyncio
async def test_unread_counts_for_staff_and_user(session: AsyncSession) -> None:
    runner = await make_user(session, "runner-support6@example.com")
    admin = await make_user(session, "admin-support6@example.com", UserRole.admin)
    await session.commit()

    ticket = await create_ticket(session, user=runner, body="Question")
    await session.commit()
    assert await unread_ticket_count_for_staff(session) == 1
    assert await unread_ticket_count_for_user(session, runner) == 0

    await mark_read_by_staff(session, ticket)
    await session.commit()
    assert await unread_ticket_count_for_staff(session) == 0

    await add_message(session, ticket, sender=admin, is_staff=True, body="Reply")
    await session.commit()
    assert await unread_ticket_count_for_user(session, runner) == 1
    assert await has_unread_for_user(session, ticket.id) is True

    await mark_read_by_reporter(session, ticket)
    await session.commit()
    assert await unread_ticket_count_for_user(session, runner) == 0
    assert await has_unread_for_user(session, ticket.id) is False


@pytest.mark.asyncio
async def test_staff_reply_emails_registered_reporter_but_not_guest_account(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[tuple[str, str]] = []

    async def fake_send_email(to: str, subject: str, body: str) -> None:
        sent.append((to, subject))

    monkeypatch.setattr("app.services.support_service.send_email", fake_send_email)

    runner = await make_user(session, "runner-support7@example.com")
    admin = await make_user(session, "admin-support7@example.com", UserRole.admin)
    await session.commit()
    ticket = await create_ticket(session, user=runner, body="Question")
    await session.commit()

    await add_message(session, ticket, sender=admin, is_staff=True, body="Answer")
    await session.commit()

    assert len(sent) == 1
    assert sent[0][0] == runner.email
