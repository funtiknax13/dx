from datetime import UTC, datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select

from app.admin.tools_common import get_tools_user, login_redirect, templates
from app.core.db import SessionLocal
from app.models.enums import ClaimStatus, UserRole
from app.models.guest_claim import GuestClaim
from app.models.user import User
from app.services.guest_service import merge_guest_into

router = APIRouter(prefix="/admin-tools", tags=["admin-tools"], include_in_schema=False)


async def _require_admin(request: Request) -> User | None:
    user = await get_tools_user(request)
    if user is None or user.role != UserRole.admin:
        return None
    return user


@router.get("/claims", response_class=HTMLResponse, response_model=None)
async def claims_queue(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        claims = list(
            await session.scalars(
                select(GuestClaim)
                .where(GuestClaim.status == ClaimStatus.pending)
                .order_by(GuestClaim.id.desc())
            )
        )
        # Resolve names in bulk rather than lazy-loading relationships post-close.
        user_ids = {c.guest_user_id for c in claims} | {c.claimant_user_id for c in claims}
        users_by_id = {
            u.id: u
            for u in await session.scalars(select(User).where(User.id.in_(user_ids)))
        }
    flash = request.query_params.get("flash")
    return templates.TemplateResponse(
        request,
        "claims.html",
        {
            "active": "claims",
            "tools_user": user,
            "claims": claims,
            "users_by_id": users_by_id,
            "flash": flash,
        },
    )


@router.post("/claims/{claim_id}/approve", response_model=None)
async def approve_claim(request: Request, claim_id: int) -> RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        claim = await session.get(GuestClaim, claim_id)
        if claim is None or claim.status != ClaimStatus.pending:
            return RedirectResponse("/admin-tools/claims", status_code=303)
        guest = await session.get(User, claim.guest_user_id)
        claimant = await session.get(User, claim.claimant_user_id)
        if guest is None or claimant is None:
            return RedirectResponse("/admin-tools/claims?flash_error=Аккаунт не найден", 303)
        try:
            await merge_guest_into(session, guest, claimant)
        except ValueError as exc:
            await session.rollback()
            return RedirectResponse(f"/admin-tools/claims?flash_error={exc}", status_code=303)
        claim.status = ClaimStatus.approved
        claim.decided_at = datetime.now(UTC)
        await session.commit()
    return RedirectResponse(
        "/admin-tools/claims?flash=Заявка подтверждена, профили объединены", 303
    )


@router.post("/claims/{claim_id}/reject", response_model=None)
async def reject_claim(request: Request, claim_id: int) -> RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        claim = await session.get(GuestClaim, claim_id)
        if claim is not None and claim.status == ClaimStatus.pending:
            claim.status = ClaimStatus.rejected
            claim.decided_at = datetime.now(UTC)
            await session.commit()
    return RedirectResponse("/admin-tools/claims?flash=Заявка отклонена", status_code=303)


@router.get("/guests", response_class=HTMLResponse, response_model=None)
async def guests_page(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()

    search_for_raw = request.query_params.get("for")
    search_for = int(search_for_raw) if search_for_raw and search_for_raw.isdigit() else None
    q = request.query_params.get("q", "").strip()

    async with SessionLocal() as session:
        guests = list(
            await session.scalars(
                select(User)
                .where(User.is_guest.is_(True), User.merged_into_id.is_(None))
                .order_by(User.id.desc())
                .limit(100)
            )
        )
        search_results: list[User] = []
        if search_for is not None and q:
            like = f"%{q}%"
            search_results = list(
                await session.scalars(
                    select(User)
                    .where(
                        User.is_guest.is_(False),
                        or_(
                            User.first_name.ilike(like),
                            User.last_name.ilike(like),
                            User.email.ilike(like),
                        ),
                    )
                    .order_by(User.id)
                    .limit(10)
                )
            )
    flash = request.query_params.get("flash")
    return templates.TemplateResponse(
        request,
        "guests.html",
        {
            "active": "guests",
            "tools_user": user,
            "guests": guests,
            "search_for": search_for,
            "search_results": search_results,
            "q": q,
            "flash": flash,
        },
    )


@router.post("/guests/{guest_id}/merge", response_model=None)
async def merge_guest(
    request: Request, guest_id: int, real_user_id: int = Form(...)
) -> RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        guest = await session.get(User, guest_id)
        real_user = await session.get(User, real_user_id)
        if guest is None or real_user is None:
            return RedirectResponse("/admin-tools/guests?flash_error=Аккаунт не найден", 303)
        try:
            await merge_guest_into(session, guest, real_user)
        except ValueError as exc:
            await session.rollback()
            return RedirectResponse(f"/admin-tools/guests?flash_error={exc}", status_code=303)
        await session.commit()
    return RedirectResponse("/admin-tools/guests?flash=Профили объединены", status_code=303)
