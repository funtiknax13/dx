from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.admin.tools_common import get_tools_user, login_redirect, require_permission, templates
from app.core.db import SessionLocal
from app.models.enums import StaffPermission, TicketStatus
from app.models.support import SupportTicket
from app.models.user import User
from app.services.staff_attention_service import (
    pending_avatar_count,
    pending_claims_count,
    pending_moderation_count,
    pending_profile_review_count,
)
from app.services.support_service import (
    add_message,
    mark_read_by_staff,
    unread_ticket_count_for_staff,
)
from app.services.survey_service import unread_response_count

router = APIRouter(prefix="/admin-tools", tags=["admin-support"], include_in_schema=False)

PAGE_SIZE = 25


async def _require_staff(request: Request) -> User | None:
    return await require_permission(request, StaffPermission.support)


@router.get("/support", response_class=HTMLResponse, response_model=None)
async def support_list(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_staff(request)
    if user is None:
        return login_redirect()

    status_filter = request.query_params.get("status", "all")
    if status_filter not in ("all", "open", "closed"):
        status_filter = "all"
    try:
        page = max(1, int(request.query_params.get("page", "1")))
    except ValueError:
        page = 1

    async with SessionLocal() as session:
        base = select(SupportTicket)
        count_base = select(func.count()).select_from(SupportTicket)
        if status_filter == "open":
            base = base.where(SupportTicket.status == TicketStatus.open)
            count_base = count_base.where(SupportTicket.status == TicketStatus.open)
        elif status_filter == "closed":
            base = base.where(SupportTicket.status == TicketStatus.closed)
            count_base = count_base.where(SupportTicket.status == TicketStatus.closed)

        total = await session.scalar(count_base) or 0
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, total_pages)

        tickets = list(
            await session.scalars(
                base.options(
                    selectinload(SupportTicket.messages), selectinload(SupportTicket.created_by)
                )
                # "open" > "closed" alphabetically, so desc() puts open tickets first.
                .order_by(SupportTicket.status.desc(), SupportTicket.id.desc())
                .offset((page - 1) * PAGE_SIZE)
                .limit(PAGE_SIZE)
            )
        )
        rows = [
            {
                "ticket": t,
                "unread": any(not m.is_staff and m.read_at is None for m in t.messages),
                # Last word is the reporter's — even if a staffer has *read* it,
                # nobody has replied yet, so it still needs attention.
                "awaiting_reply": bool(t.messages) and not t.messages[-1].is_staff,
                "last_message": t.messages[-1] if t.messages else None,
            }
            for t in tickets
        ]
    return templates.TemplateResponse(
        request,
        "support_list.html",
        {
            "active": "support",
            "tools_user": user,
            "rows": rows,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "status_filter": status_filter,
        },
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
    # Deliberately get_tools_user (any organizer/admin), not _require_staff
    # (support-only) — this endpoint aggregates several independently
    # gated counts, so a single missing permission must only zero out its
    # own key below, not the whole response.
    user = await get_tools_user(request)
    empty = {
        "tickets": 0,
        "surveys": 0,
        "claims": 0,
        "moderation": 0,
        "avatars": 0,
        "profile_review": 0,
    }
    if user is None:
        return empty
    # get_tools_user already attached granted_permissions — each key below
    # only shows a badge if this admin-tools user actually has the matching
    # StaffPermission (always true for admin, per-organizer otherwise).
    perms = user.granted_permissions
    async with SessionLocal() as session:
        tickets = (
            await unread_ticket_count_for_staff(session) if StaffPermission.support in perms else 0
        )
        surveys = await unread_response_count(session) if StaffPermission.surveys in perms else 0
        claims = await pending_claims_count(session) if StaffPermission.guest_claims in perms else 0
        moderation = (
            await pending_moderation_count(session)
            if StaffPermission.results_review in perms
            else 0
        )
        avatars = await pending_avatar_count(session) if StaffPermission.avatars in perms else 0
        profile_review = (
            await pending_profile_review_count(session)
            if StaffPermission.profile_review in perms
            else 0
        )
    return {
        "tickets": tickets,
        "surveys": surveys,
        "claims": claims,
        "moderation": moderation,
        "avatars": avatars,
        "profile_review": profile_review,
    }
