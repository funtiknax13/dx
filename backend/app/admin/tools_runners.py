from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from app.admin.tools_common import get_tools_user, login_redirect, templates
from app.core.db import SessionLocal
from app.models.enums import UserRole
from app.models.user import User
from app.services.name_search import flexible_name_filter

router = APIRouter(prefix="/admin-tools", tags=["admin-runners"], include_in_schema=False)

PAGE_SIZE = 25


async def _require_admin(request: Request) -> User | None:
    """A full profile lookup (every field but the password hash) is
    sensitive enough to stay a hard admin check, not a delegable
    StaffPermission — unlike the rest of admin-tools, no organizer gets
    this even if granted everything else."""
    user = await get_tools_user(request)
    if user is None or user.role != UserRole.admin:
        return None
    return user


@router.get("/runners", response_class=HTMLResponse, response_model=None)
async def runners_lookup(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()

    q = request.query_params.get("q", "").strip()
    try:
        page = max(1, int(request.query_params.get("page", "1")))
    except ValueError:
        page = 1

    async with SessionLocal() as session:
        base = select(User).where(User.is_guest.is_(False))
        count_base = select(func.count()).select_from(User).where(User.is_guest.is_(False))
        if q:
            base = base.where(flexible_name_filter(q))
            count_base = count_base.where(flexible_name_filter(q))

        total = await session.scalar(count_base) or 0
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, total_pages)

        users = list(
            await session.scalars(
                base.order_by(User.id).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
            )
        )
    return templates.TemplateResponse(
        request,
        "runners.html",
        {
            "active": "runners",
            "tools_user": user,
            "users": users,
            "q": q,
            "total": total,
            "page": page,
            "total_pages": total_pages,
        },
    )


@router.get("/runners/{user_id}", response_class=HTMLResponse, response_model=None)
async def runner_detail(request: Request, user_id: int) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        target = await session.get(User, user_id)
        if target is None or target.is_guest:
            return RedirectResponse("/admin-tools/runners", status_code=303)
    return templates.TemplateResponse(
        request, "runner_detail.html", {"active": "runners", "tools_user": user, "u": target}
    )
