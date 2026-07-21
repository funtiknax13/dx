from datetime import UTC, datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email import send_email
from app.models.enums import TicketStatus
from app.models.support import SupportMessage, SupportTicket
from app.models.user import User


async def create_ticket(
    session: AsyncSession,
    *,
    user: User | None,
    body: str,
    guest_name: str | None = None,
    guest_contact: str | None = None,
) -> SupportTicket:
    """Start a new ticket with its first message. `user` is None for an
    anonymous reporter (someone with no account, e.g. stuck registering) —
    guest_name is required in that case so staff know who they're talking to."""
    ticket = SupportTicket(
        status=TicketStatus.open,
        created_by_user_id=user.id if user else None,
        guest_name=None if user else guest_name,
        guest_contact=None if user else guest_contact,
    )
    session.add(ticket)
    await session.flush()
    session.add(
        SupportMessage(
            ticket_id=ticket.id,
            sender_user_id=user.id if user else None,
            is_staff=False,
            body=body,
        )
    )
    await session.flush()
    return ticket


async def add_message(
    session: AsyncSession,
    ticket: SupportTicket,
    *,
    sender: User | None,
    is_staff: bool,
    body: str,
) -> SupportMessage:
    """A new message from the reporter reopens a closed ticket — staff
    replying to an already-closed ticket does not (that's a deliberate
    "closing note", not a sign the issue is unresolved again)."""
    message = SupportMessage(
        ticket_id=ticket.id,
        sender_user_id=sender.id if sender else None,
        is_staff=is_staff,
        body=body,
    )
    session.add(message)
    if not is_staff and ticket.status == TicketStatus.closed:
        ticket.status = TicketStatus.open
    await session.flush()

    if is_staff and ticket.created_by_user_id is not None:
        recipient = await session.get(User, ticket.created_by_user_id)
        if recipient is not None and not recipient.is_guest:
            link = f"{settings.frontend_origin}/support/tickets/{ticket.id}"
            await send_email(
                recipient.email,
                "Вам ответили в поддержке DH",
                f"Здравствуйте, {recipient.first_name}!\n\n"
                f"На ваше обращение в поддержку DH пришёл ответ:\n\n{body}\n\n"
                f"Посмотреть и ответить: {link}",
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
