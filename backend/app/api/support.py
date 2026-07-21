from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, OptionalUser, SessionDep
from app.models.support import SupportTicket
from app.models.user import User
from app.schemas.support import (
    SupportMessageCreate,
    SupportMessageOut,
    SupportTicketCreate,
    SupportTicketDetailOut,
    SupportTicketOut,
)
from app.services.support_service import (
    add_message,
    create_ticket,
    has_unread_for_user,
    mark_read_by_reporter,
    unread_ticket_count_for_user,
)

router = APIRouter(prefix="/support", tags=["support"])


def _preview(ticket: SupportTicket) -> str:
    first = ticket.messages[0].body if ticket.messages else ""
    return first[:120]


@router.post("/tickets", response_model=SupportTicketOut, status_code=status.HTTP_201_CREATED)
async def create_support_ticket(
    payload: SupportTicketCreate, user: OptionalUser, session: SessionDep
) -> SupportTicketOut:
    if user is None and not (payload.guest_name or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Укажите имя")
    ticket = await create_ticket(
        session,
        user=user,
        body=payload.body,
        guest_name=payload.guest_name,
        guest_contact=payload.guest_contact,
    )
    await session.commit()
    return SupportTicketOut(
        id=ticket.id,
        status=ticket.status.value,
        created_at=ticket.created_at,
        preview=payload.body[:120],
        has_unread=False,
    )


@router.get("/tickets", response_model=list[SupportTicketOut])
async def my_support_tickets(user: CurrentUser, session: SessionDep) -> list[SupportTicketOut]:
    tickets = list(
        await session.scalars(
            select(SupportTicket)
            .where(SupportTicket.created_by_user_id == user.id)
            .options(selectinload(SupportTicket.messages))
            .order_by(SupportTicket.id.desc())
        )
    )
    return [
        SupportTicketOut(
            id=t.id,
            status=t.status.value,
            created_at=t.created_at,
            preview=_preview(t),
            has_unread=await has_unread_for_user(session, t.id),
        )
        for t in tickets
    ]


@router.get("/tickets/unread-count")
async def support_unread_count(user: CurrentUser, session: SessionDep) -> dict[str, int]:
    return {"count": await unread_ticket_count_for_user(session, user)}


async def _get_owned_ticket(session: AsyncSession, ticket_id: int, user: User) -> SupportTicket:
    ticket = await session.get(
        SupportTicket, ticket_id, options=[selectinload(SupportTicket.messages)]
    )
    if ticket is None or ticket.created_by_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return ticket


@router.get("/tickets/{ticket_id}", response_model=SupportTicketDetailOut)
async def support_ticket_detail(
    ticket_id: int, user: CurrentUser, session: SessionDep
) -> SupportTicketDetailOut:
    ticket = await _get_owned_ticket(session, ticket_id, user)
    await mark_read_by_reporter(session, ticket)
    await session.commit()
    return SupportTicketDetailOut(
        id=ticket.id,
        status=ticket.status.value,
        created_at=ticket.created_at,
        messages=[
            SupportMessageOut(
                id=m.id, is_staff=m.is_staff, body=m.body, created_at=m.created_at
            )
            for m in ticket.messages
        ],
    )


@router.post("/tickets/{ticket_id}/messages", response_model=SupportTicketDetailOut)
async def add_support_message(
    ticket_id: int, payload: SupportMessageCreate, user: CurrentUser, session: SessionDep
) -> SupportTicketDetailOut:
    ticket = await _get_owned_ticket(session, ticket_id, user)
    await add_message(session, ticket, sender=user, is_staff=False, body=payload.body)
    await session.commit()
    await session.refresh(ticket, attribute_names=["messages"])
    return SupportTicketDetailOut(
        id=ticket.id,
        status=ticket.status.value,
        created_at=ticket.created_at,
        messages=[
            SupportMessageOut(
                id=m.id, is_staff=m.is_staff, body=m.body, created_at=m.created_at
            )
            for m in ticket.messages
        ],
    )
