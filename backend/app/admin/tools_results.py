from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.admin.tools_common import get_tools_user, login_redirect, templates
from app.core.config import settings
from app.core.db import SessionLocal
from app.models.attendance import AttendanceRecord
from app.models.enums import ModerationStatus, UserRole
from app.models.group import Group
from app.models.result import Result

router = APIRouter(prefix="/admin-tools", tags=["admin-tools"], include_in_schema=False)

PAGE_SIZE = 25


@router.get("/results", response_class=HTMLResponse, response_model=None)
async def results_pending(request: Request) -> HTMLResponse | RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    if user.role != UserRole.admin:
        # Result approval is an Admin-only function per CLAUDE.md.
        return RedirectResponse("/admin-tools", status_code=303)

    try:
        page = max(1, int(request.query_params.get("page", "1")))
    except ValueError:
        page = 1

    async with SessionLocal() as session:
        total = await session.scalar(
            select(func.count())
            .select_from(Result)
            .where(Result.status == ModerationStatus.pending)
        )
        total = total or 0
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, total_pages)
        results = list(
            await session.scalars(
                select(Result)
                .where(Result.status == ModerationStatus.pending)
                .options(
                    selectinload(Result.attendance_record).options(
                        selectinload(AttendanceRecord.group).selectinload(Group.event),
                        selectinload(AttendanceRecord.runner),
                    ),
                )
                .order_by(Result.id.desc())
                .offset((page - 1) * PAGE_SIZE)
                .limit(PAGE_SIZE)
            )
        )
    flash = request.query_params.get("flash")
    return templates.TemplateResponse(
        request,
        "results_pending.html",
        {
            "active": "results",
            "tools_user": user,
            "results": results,
            "flash": flash,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "distance_tol_pct": settings.result_distance_tolerance_pct,
            "start_tol_min": settings.result_start_time_tolerance_minutes,
        },
    )


@router.post("/results/{result_id}/approve", response_model=None)
async def approve_result(request: Request, result_id: int) -> RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    if user.role != UserRole.admin:
        return RedirectResponse("/admin-tools", status_code=303)
    async with SessionLocal() as session:
        result = await session.get(Result, result_id)
        if result is not None:
            result.status = ModerationStatus.approved
            await session.commit()
    return RedirectResponse("/admin-tools/results?flash=Результат подтверждён", status_code=303)


@router.post("/results/{result_id}/reject", response_model=None)
async def reject_result(request: Request, result_id: int) -> RedirectResponse:
    """Delete a bogus/duplicate result so the runner can resubmit — CLAUDE.md doesn't
    define a distinct 'rejected' status, and leaving it pending forever would just
    clutter the queue."""
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    if user.role != UserRole.admin:
        return RedirectResponse("/admin-tools", status_code=303)
    async with SessionLocal() as session:
        result = await session.get(Result, result_id)
        if result is not None:
            await session.delete(result)
            await session.commit()
    return RedirectResponse(
        "/admin-tools/results?flash=Результат отклонён и удалён", status_code=303
    )
