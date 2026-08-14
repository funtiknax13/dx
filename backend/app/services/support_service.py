from datetime import UTC, datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email import render_email_html, send_email
from app.models.enums import TicketStatus
from app.models.support import SupportMessage, SupportTicket
from app.models.user import User


async def create_ticket(
    session: AsyncSession,
    *,
    user: User,
    body: str,
) -> SupportTicket:
    """Start a new ticket with its first message. Support is for logged-in users
    only (the guest_name/guest_contact columns remain for legacy/anonymized
    tickets, but new tickets always have an account)."""
    ticket = SupportTicket(
        status=TicketStatus.open,
        created_by_user_id=user.id,
    )
    session.add(ticket)
    await session.flush()
    session.add(
        SupportMessage(
            ticket_id=ticket.id,
            sender_user_id=user.id,
            is_staff=False,
            body=body,
        )
    )
    await session.flush()
    return ticket


async def create_staff_ticket(
    session: AsyncSession,
    *,
    recipient: User,
    admin: User | None,
    body: str,
    closed: bool = True,
) -> SupportTicket:
    """A ticket staff opens *to* a runner (the reverse of the usual flow) — e.g.
    to tell them a submitted result wasn't accepted at moderation. Opens already
    resolved (closed) with a single staff message; the runner gets the same
    notification email as any staff reply (see add_message) and can still reply
    to reopen the thread if they want to discuss it."""
    ticket = SupportTicket(
        status=TicketStatus.closed if closed else TicketStatus.open,
        created_by_user_id=recipient.id,
    )
    session.add(ticket)
    await session.flush()
    await add_message(session, ticket, sender=admin, is_staff=True, body=body)
    return ticket


async def add_message(
    session: AsyncSession,
    ticket: SupportTicket,
    *,
    sender: User | None,
    is_staff: bool,
    body: str,
) -> SupportMessage:
    """Append a message. A staff-closed ticket is not reopened here — only staff
    can reopen it (the reporter-reply endpoint blocks replies once closed), so a
    resolved thread stays resolved."""
    message = SupportMessage(
        ticket_id=ticket.id,
        sender_user_id=sender.id if sender else None,
        is_staff=is_staff,
        body=body,
    )
    session.add(message)
    await session.flush()

    if is_staff and ticket.created_by_user_id is not None:
        recipient = await session.get(User, ticket.created_by_user_id)
        if recipient is not None and not recipient.is_guest:
            link = f"{settings.frontend_origin}/support/tickets/{ticket.id}"
            await send_email(
                recipient.email,
                "Ответ в поддержке — DАЙ ХАРD Чебоксары",
                f"Здравствуйте, {recipient.first_name}!\n\n"
                f"На ваше обращение в поддержку DАЙ ХАРD пришёл ответ:\n\n{body}\n\n"
                f"Посмотреть и ответить: {link}",
                render_email_html(
                    "support_reply.html",
                    first_name=recipient.first_name,
                    reply_body=body,
                    link=link,
                ),
            )
    return message


async def mark_read_by_staff(session: AsyncSession, ticket: SupportTicket) -> None:
    unread = await session.scalars(
        select(SupportMessage).where(
            SupportMessage.ticket_id == ticket.id,
            SupportMessage.is_staff.is_(False),
            SupportMessage.read_at.is_(None),
        )
    )
    now = datetime.now(UTC)
    for message in unread:
        message.read_at = now


async def mark_read_by_reporter(session: AsyncSession, ticket: SupportTicket) -> None:
    unread = await session.scalars(
        select(SupportMessage).where(
            SupportMessage.ticket_id == ticket.id,
            SupportMessage.is_staff.is_(True),
            SupportMessage.read_at.is_(None),
        )
    )
    now = datetime.now(UTC)
    for message in unread:
        message.read_at = now


async def unread_ticket_count_for_user(session: AsyncSession, user: User) -> int:
    """How many of `user`'s own tickets have an unread staff reply — the
    badge shown next to "Поддержка" in the site header."""
    result = await session.scalars(
        select(SupportTicket.id)
        .join(SupportMessage, SupportMessage.ticket_id == SupportTicket.id)
        .where(
            SupportTicket.created_by_user_id == user.id,
            SupportMessage.is_staff.is_(True),
            SupportMessage.read_at.is_(None),
        )
        .distinct()
    )
    return len(list(result))


async def unread_ticket_count_for_staff(session: AsyncSession) -> int:
    """How many tickets have an unread message from the reporter's side —
    the red admin-tools nav badge. Shared across all staff (team inbox)."""
    result = await session.scalars(
        select(SupportTicket.id)
        .join(SupportMessage, SupportMessage.ticket_id == SupportTicket.id)
        .where(SupportMessage.is_staff.is_(False), SupportMessage.read_at.is_(None))
        .distinct()
    )
    return len(list(result))


async def has_unread_for_user(session: AsyncSession, ticket_id: int) -> bool:
    result = await session.scalar(
        select(
            exists().where(
                SupportMessage.ticket_id == ticket_id,
                SupportMessage.is_staff.is_(True),
                SupportMessage.read_at.is_(None),
            )
        )
    )
    return bool(result)
