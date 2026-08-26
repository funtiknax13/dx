from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.admin.tools_common import get_tools_user, login_redirect, templates
from app.core.config import settings
from app.core.db import SessionLocal
from app.models.attendance import AttendanceRecord
from app.models.enums import ModerationStatus, StaffPermission
from app.models.group import Group
from app.models.result import Result
from app.services.support_service import create_staff_ticket

router = APIRouter(prefix="/admin-tools", tags=["admin-tools"], include_in_schema=False)

PAGE_SIZE = 25


@router.get("/results", response_class=HTMLResponse, response_model=None)
async def results_pending(request: Request) -> HTMLResponse | RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    if StaffPermission.results_review not in user.granted_permissions:
        # Admin by default, delegable to an organizer via StaffPermission.results_review.
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
    if StaffPermission.results_review not in user.granted_permissions:
        return RedirectResponse("/admin-tools", status_code=303)
    async with SessionLocal() as session:
        result = await session.get(Result, result_id)
        if result is not None:
            result.status = ModerationStatus.approved
            await session.commit()
    return RedirectResponse("/admin-tools/results?flash=Результат подтверждён", status_code=303)


def _rejection_message(result: Result, record: AttendanceRecord | None, reason: str) -> str:
    """The body of the closed support ticket a runner gets when their result is
    rejected — names the run so they know which one, plus the admin's reason."""
    group = record.group if record is not None else None
    event = group.event if group is not None else None
    dur = result.duration_seconds
    lines = ["Ваш результат не принят по итогам проверки.", ""]
    if event is not None:
        lines.append(f"Событие: {event.title}")
    if group is not None:
        lines.append(f"Группа: {group.name}")
    lines.append(
        f"Результат: {result.distance_km:.2f} км, "
        f"{dur // 3600}:{dur % 3600 // 60:02d}:{dur % 60:02d}"
    )
    reason = reason.strip()
    if reason:
        lines += ["", f"Причина: {reason}"]
    lines += ["", "Вы можете загрузить результат заново, устранив замечание."]
    return "\n".join(lines)


@router.post("/results/{result_id}/reject", response_model=None)
async def reject_result(
    request: Request, result_id: int, reason: str = Form("")
) -> RedirectResponse:
    """Turn a result down: mark it `rejected` (a distinct, kept status — not a
    delete) so the runner sees it wasn't accepted and can upload a corrected one,
    and tell them why via a closed support ticket. A rejected result never counts
    toward the protocol/rating, but stays visible instead of silently vanishing."""
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    if StaffPermission.results_review not in user.granted_permissions:
        return RedirectResponse("/admin-tools", status_code=303)
    async with SessionLocal() as session:
        result = await session.scalar(
            select(Result)
            .where(Result.id == result_id)
            .options(
                selectinload(Result.attendance_record).options(
                    selectinload(AttendanceRecord.group).selectinload(Group.event),
                    selectinload(AttendanceRecord.runner),
                )
            )
        )
        if result is None:
            return RedirectResponse(
                "/admin-tools/results?flash=Результат не найден", status_code=303
            )
        record = result.attendance_record
        runner = record.runner if record is not None else None
        # Only real accounts can receive a ticket (guests/unmatched can't log in).
        if runner is not None and not runner.is_guest:
            await create_staff_ticket(
                session,
                recipient=runner,
                admin=user,
                body=_rejection_message(result, record, reason),
            )
        result.status = ModerationStatus.rejected
        await session.commit()
    return RedirectResponse(
        "/admin-tools/results?flash=Результат отклонён, бегун уведомлён", status_code=303
    )
