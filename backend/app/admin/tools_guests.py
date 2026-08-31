from datetime import UTC, datetime

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import func, select

from app.admin.tools_common import login_redirect, require_permission, templates
from app.core.db import SessionLocal
from app.models.enums import ClaimStatus, StaffPermission
from app.models.guest_claim import GuestClaim
from app.models.user import User
from app.services.guest_service import merge_guest_into
from app.services.name_search import flexible_name_filter

router = APIRouter(prefix="/admin-tools", tags=["admin-tools"], include_in_schema=False)

GUEST_PAGE_SIZE = 25


async def _require_access(request: Request) -> User | None:
    return await require_permission(request, StaffPermission.guest_claims)


@router.get("/claims", response_class=HTMLResponse, response_model=None)
async def claims_queue(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_access(request)
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
            u.id: u for u in await session.scalars(select(User).where(User.id.in_(user_ids)))
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
    user = await _require_access(request)
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
    user = await _require_access(request)
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
    user = await _require_access(request)
    if user is None:
        return login_redirect()

    q = request.query_params.get("q", "").strip()
    try:
        page = max(1, int(request.query_params.get("page", "1")))
    except ValueError:
        page = 1

    async with SessionLocal() as session:
        base = select(User).where(User.is_guest.is_(True), User.merged_into_id.is_(None))
        count_base = (
            select(func.count())
            .select_from(User)
            .where(User.is_guest.is_(True), User.merged_into_id.is_(None))
        )
        if q:
            base = base.where(flexible_name_filter(q))
            count_base = count_base.where(flexible_name_filter(q))

        total = await session.scalar(count_base) or 0
        total_pages = max(1, (total + GUEST_PAGE_SIZE - 1) // GUEST_PAGE_SIZE)
        page = min(page, total_pages)

        guests = list(
            await session.scalars(
                base.order_by(User.id.desc())
                .offset((page - 1) * GUEST_PAGE_SIZE)
                .limit(GUEST_PAGE_SIZE)
            )
        )
    flash = request.query_params.get("flash")
    flash_error = request.query_params.get("flash_error")
    return templates.TemplateResponse(
        request,
        "guests.html",
        {
            "active": "guests",
            "tools_user": user,
            "guests": guests,
            "q": q,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "flash": flash,
            "flash_error": flash_error,
        },
    )


@router.get("/guests/{guest_id}", response_class=HTMLResponse, response_model=None)
async def guest_detail(
    request: Request, guest_id: int
) -> HTMLResponse | RedirectResponse | PlainTextResponse:
    """Serves both the full page and the fragment the guests-list modal
    fetches (?partial=1) — same dual-purpose pattern as tools_runners.py's
    runner_detail. `q` here searches *registered* accounts to merge this
    guest into, unrelated to the guest-name search on the list page."""
    partial = request.query_params.get("partial") == "1"
    user = await _require_access(request)
    if user is None:
        if partial:
            return PlainTextResponse("Forbidden", status_code=status.HTTP_403_FORBIDDEN)
        return login_redirect()

    q = request.query_params.get("q", "").strip()
    async with SessionLocal() as session:
        guest = await session.get(User, guest_id)
        if guest is None or not guest.is_guest or guest.merged_into_id is not None:
            if partial:
                return PlainTextResponse("Not found", status_code=status.HTTP_404_NOT_FOUND)
            return RedirectResponse("/admin-tools/guests", status_code=303)
        search_results: list[User] = []
        if q:
            search_results = list(
                await session.scalars(
                    select(User)
                    .where(User.is_guest.is_(False), flexible_name_filter(q))
                    .order_by(User.id)
                    .limit(10)
                )
            )
    ctx = {"g": guest, "q": q, "search_results": search_results}
    if partial:
        return templates.TemplateResponse(request, "_guest_detail_fragment.html", ctx)
    return templates.TemplateResponse(
        request,
        "guest_detail.html",
        {
            **ctx,
            "active": "guests",
            "tools_user": user,
            "flash": request.query_params.get("flash"),
            "flash_error": request.query_params.get("flash_error"),
        },
    )


@router.post("/guests/{guest_id}/rename", response_model=None)
async def rename_guest(
    request: Request,
    guest_id: int,
    # Not Form(...): an empty submitted value parses as an absent field (the
    # browser still sends `first_name=`, but Starlette's urlencoded form
    # parsing drops blank values), which would 422 before the friendly
    # empty-check below ever runs.
    first_name: str = Form(default=""),
    last_name: str = Form(default=""),
) -> RedirectResponse:
    user = await _require_access(request)
    if user is None:
        return login_redirect()
    first_name = first_name.strip()
    last_name = last_name.strip()
    if not first_name or not last_name:
        return RedirectResponse(
            f"/admin-tools/guests/{guest_id}?flash_error=Имя и фамилия не могут быть пустыми",
            303,
        )
    async with SessionLocal() as session:
        guest = await session.get(User, guest_id)
        if guest is None or not guest.is_guest:
            return RedirectResponse("/admin-tools/guests?flash_error=Профиль не найден", 303)
        guest.first_name = first_name
        guest.last_name = last_name
        await session.commit()
    return RedirectResponse(f"/admin-tools/guests/{guest_id}?flash=Имя обновлено", status_code=303)


@router.post("/guests/{guest_id}/merge", response_model=None)
async def merge_guest(
    request: Request, guest_id: int, real_user_id: int = Form(...)
) -> RedirectResponse:
    user = await _require_access(request)
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
