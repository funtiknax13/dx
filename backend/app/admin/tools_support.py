from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.admin.tools_common import get_tools_user, login_redirect, templates
from app.core.db import SessionLocal
from app.models.enums import TicketStatus, UserRole
from app.models.support import SupportTicket
from app.models.user import User
from app.services.staff_attention_service import pending_claims_count, pending_moderation_count
from app.services.support_service import (
    add_message,
    mark_read_by_staff,
    unread_ticket_count_for_staff,
)
from app.services.survey_service import unread_response_count

router = APIRouter(prefix="/admin-tools", tags=["admin-support"], include_in_schema=False)


async def _require_staff(request: Request) -> User | None:
    """Unlike surveys/CSV-import/moderation, tickets are visible to both
    organizer and admin — get_tools_user already restricts to those two roles."""
    return await get_tools_user(request)


@router.get("/support", response_class=HTMLResponse, response_model=None)
async def support_list(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_staff(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        tickets = list(
            await session.scalars(
                select(SupportTicket)
                .options(
                    selectinload(SupportTicket.messages), selectinload(SupportTicket.created_by)
                )
                # "open" > "closed" alphabetically, so desc() puts open tickets first.
                .order_by(SupportTicket.status.desc(), SupportTicket.id.desc())
            )
        )
        rows = [
            {
                "ticket": t,
                "unread": any(
                    not m.is_staff and m.read_at is None for m in t.messages
                ),
                "last_message": t.messages[-1] if t.messages else None,
            }
            for t in tickets
        ]
    return templates.TemplateResponse(
        request,
        "support_list.html",
        {"active": "support", "tools_user": user, "rows": rows},
    )


@router.get("/support/{ticket_id}", response_class=HTMLResponse, response_model=None)
async def support_detail(request: Request, ticket_id: int) -> HTMLResponse | RedirectResponse:
    user = await _require_staff(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        ticket = await session.get(
            SupportTicket,
            ticket_id,
            options=[selectinload(SupportTicket.messages), selectinload(SupportTicket.created_by)],
        )
        if ticket is None:
            return RedirectResponse("/admin-tools/support", status_code=303)
        await mark_read_by_staff(session, ticket)
        await session.commit()
        await session.refresh(ticket, attribute_names=["messages"])
    flash = request.query_params.get("flash")
    return templates.TemplateResponse(
        request,
        "support_detail.html",
        {"active": "support", "tools_user": user, "ticket": ticket, "flash": flash},
    )


@router.post("/support/{ticket_id}/reply", response_model=None)
async def support_reply(
    request: Request, ticket_id: int, body: str = Form(...)
) -> RedirectResponse:
    user = await _require_staff(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        if ticket is None:
            return RedirectResponse("/admin-tools/support", status_code=303)
        if ticket.created_by_user_id is None:
            flash_error = "Анонимному обращению нельзя ответить в приложении"
            return RedirectResponse(
                f"/admin-tools/support/{ticket_id}?flash_error={flash_error}",
                status_code=303,
            )
        await add_message(session, ticket, sender=user, is_staff=True, body=body)
        await session.commit()
    return RedirectResponse(f"/admin-tools/support/{ticket_id}?flash=Ответ отправлен", 303)


@router.post("/support/{ticket_id}/status", response_model=None)
async def support_toggle_status(request: Request, ticket_id: int) -> RedirectResponse:
    user = await _require_staff(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        if ticket is None:
            return RedirectResponse("/admin-tools/support", status_code=303)
        ticket.status = (
            TicketStatus.closed if ticket.status == TicketStatus.open else TicketStatus.open
        )
        await session.commit()
    return RedirectResponse(f"/admin-tools/support/{ticket_id}", status_code=303)


@router.get("/badge-counts", response_model=None)
async def badge_counts(request: Request) -> dict[str, int]:
    user = await _require_staff(request)
    if user is None:
        return {"tickets": 0, "surveys": 0, "claims": 0, "moderation": 0}
    async with SessionLocal() as session:
        tickets = await unread_ticket_count_for_staff(session)
        if user.role != UserRole.admin:
            # Surveys/claims/moderation are Admin-only queues (see CLAUDE.md) —
            # an organizer has no nav link for them, so no badge either.
            return {"tickets": tickets, "surveys": 0, "claims": 0, "moderation": 0}
        surveys = await unread_response_count(session)
        claims = await pending_claims_count(session)
        moderation = await pending_moderation_count(session)
    return {"tickets": tickets, "surveys": surveys, "claims": claims, "moderation": moderation}
