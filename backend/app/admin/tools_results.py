from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.admin.tools_common import get_tools_user, login_redirect, templates
from app.core.config import settings
from app.core.db import SessionLocal
from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, ModerationStatus, StaffPermission, UserRole
from app.models.event import Event
from app.models.group import Group
from app.models.result import Result
from app.models.user import User
from app.services.name_search import flexible_name_filter
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
            "distance_mismatch_km": settings.result_distance_mismatch_km,
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


def _dnf_message(result: Result, record: AttendanceRecord | None) -> str:
    """The body of the closed support ticket a runner gets when their result is
    accepted but re-classified as DNF — names the run and the distance gap
    that led to the call, same spirit as _rejection_message."""
    group = record.group if record is not None else None
    event = group.event if group is not None else None
    dur = result.duration_seconds
    lines = [
        "Ваш результат принят, но засчитан как сход с дистанции (DNF) — "
        "пройденная дистанция заметно меньше дистанции группы.",
        "",
    ]
    if event is not None:
        lines.append(f"Событие: {event.title}")
    if group is not None:
        lines.append(f"Группа: {group.name} ({group.target_distance_km:g} км)")
    lines.append(
        f"Результат: {result.distance_km:.2f} км, "
        f"{dur // 3600}:{dur % 3600 // 60:02d}:{dur % 60:02d}"
    )
    lines += [
        "",
        "Если это не так и вы прошли полную дистанцию — напишите в поддержку.",
    ]
    return "\n".join(lines)


@router.post("/results/{result_id}/approve-dnf", response_model=None)
async def approve_result_as_dnf(request: Request, result_id: int) -> RedirectResponse:
    """Accept a result but record it as a DNF rather than a finish — for a
    runner who ran a shorter, honestly-reported distance (cut the route
    short, didn't fully claim "I finished"). Unlike reject_result, this
    settles the result rather than asking for a re-upload: both the record's
    and the result's finish_status flip together (finish_status is normally
    decided once at CSV import and never recomputed from a result — this is
    the one deliberate, human-reviewed exception, see CLAUDE.md)."""
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
        if result.status != ModerationStatus.pending:
            return RedirectResponse(
                "/admin-tools/results?flash=Результат уже обработан", status_code=303
            )
        record = result.attendance_record
        runner = record.runner if record is not None else None
        if record is not None:
            record.finish_status = FinishStatus.dnf
        result.finish_status = FinishStatus.dnf
        result.status = ModerationStatus.approved
        if runner is not None and not runner.is_guest:
            await create_staff_ticket(
                session,
                recipient=runner,
                admin=user,
                body=_dnf_message(result, record),
            )
        await session.commit()
    return RedirectResponse(
        "/admin-tools/results?flash=Результат принят со статусом DNF, бегун уведомлён",
        status_code=303,
    )


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
        if result.status != ModerationStatus.pending:
            # Already acted on — a double click/submit (the reason-modal form has
            # no client-side guard against it) must not send a second ticket.
            return RedirectResponse(
                "/admin-tools/results?flash=Результат уже обработан", status_code=303
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


def _status_fix_message(record: AttendanceRecord, new_status: FinishStatus) -> str:
    """Sent when an admin corrects finish_status on an already-settled
    record (e.g. a result that slipped through as "finished" but was
    actually a DNF) — distinct from _dnf_message above, which only ever
    fires for a still-pending result. Named by direction rather than always
    "DNF" since this same action also undoes a wrong DNF back to a finish."""
    group = record.group
    event = group.event
    became = "сход с дистанции (DNF)" if new_status == FinishStatus.dnf else "финиш"
    lines = [
        f"Статус вашей пробежки скорректирован — теперь засчитан как {became}.",
        "",
        f"Событие: {event.title}",
        f"Группа: {group.name}",
        "",
        "Если это ошибка — напишите в поддержку.",
    ]
    return "\n".join(lines)


async def _set_finish_status(
    session: AsyncSession, record: AttendanceRecord, new_status: FinishStatus, admin: User
) -> bool:
    """Flips finish_status on an already-settled AttendanceRecord (and its
    Result, if any — same sync csv_import_service does on a re-import,
    see CLAUDE.md's one sanctioned exception to "never recomputed"). Unlike
    approve_result_as_dnf, this doesn't require — or touch — moderation
    status: the record may already be approved, or have no Result at all
    (a CSV-only participation), and stays exactly as settled as it was.
    Returns False (no-op) when the record is already at new_status."""
    if record.finish_status == new_status:
        return False
    record.finish_status = new_status
    if record.result is not None:
        record.result.finish_status = new_status
    if record.runner is not None and not record.runner.is_guest:
        await create_staff_ticket(
            session,
            recipient=record.runner,
            admin=admin,
            body=_status_fix_message(record, new_status),
        )
    return True


@router.get("/results/fix", response_class=HTMLResponse, response_model=None)
async def results_fix_search(request: Request) -> HTMLResponse | RedirectResponse:
    """A standalone search-and-correct panel for a record that's already
    settled (visible in the protocol) rather than still pending — SQLAdmin
    can edit the same columns, but finding the one row by name among every
    AttendanceRecord, and keeping Result's finish_status in sync by hand,
    isn't realistically "easy". Scoped like the rest of admin-tools: an
    organizer only ever sees/fixes their own events."""
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    if StaffPermission.results_review not in user.granted_permissions:
        return RedirectResponse("/admin-tools", status_code=303)

    q = request.query_params.get("q", "").strip()
    raw_event_id = request.query_params.get("event_id")
    try:
        event_id = int(raw_event_id) if raw_event_id else None
    except ValueError:
        event_id = None

    async with SessionLocal() as session:
        events_stmt = select(Event).order_by(Event.date.desc())
        if user.role != UserRole.admin:
            events_stmt = events_stmt.where(Event.created_by == user.id)
        events = list(await session.scalars(events_stmt))

        records: list[AttendanceRecord] = []
        if q:
            stmt = (
                select(AttendanceRecord)
                .join(Group, Group.id == AttendanceRecord.group_id)
                .join(Event, Event.id == Group.event_id)
                .outerjoin(User, User.id == AttendanceRecord.runner_id)
                .where(or_(flexible_name_filter(q), AttendanceRecord.raw_name.ilike(f"%{q}%")))
                .options(
                    selectinload(AttendanceRecord.group).selectinload(Group.event),
                    selectinload(AttendanceRecord.runner),
                    selectinload(AttendanceRecord.result),
                )
                .order_by(Event.date.desc())
                .limit(50)
            )
            if user.role != UserRole.admin:
                stmt = stmt.where(Event.created_by == user.id)
            if event_id is not None:
                stmt = stmt.where(Event.id == event_id)
            records = list(await session.scalars(stmt))

    return templates.TemplateResponse(
        request,
        "results_fix.html",
        {
            "active": "results",
            "tools_user": user,
            "events": events,
            "q": q,
            "event_id": event_id,
            "records": records,
            "flash": request.query_params.get("flash"),
        },
    )


def _fix_redirect(q: str, event_id: str, flash: str) -> RedirectResponse:
    query: dict[str, str] = {"flash": flash}
    if q:
        query["q"] = q
    if event_id:
        query["event_id"] = event_id
    return RedirectResponse(f"/admin-tools/results/fix?{urlencode(query)}", status_code=303)


@router.post("/results/fix/{record_id}/set-dnf", response_model=None)
async def results_fix_set_dnf(
    request: Request, record_id: int, q: str = Form(""), event_id: str = Form("")
) -> RedirectResponse:
    # q/event_id round-trip through hidden form fields (see results_fix.html)
    # rather than the URL, so the search context survives a POST back to the
    # same page instead of resetting to an empty, query-less list.
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    if StaffPermission.results_review not in user.granted_permissions:
        return RedirectResponse("/admin-tools", status_code=303)
    async with SessionLocal() as session:
        record = await session.scalar(
            select(AttendanceRecord)
            .where(AttendanceRecord.id == record_id)
            .options(
                selectinload(AttendanceRecord.group).selectinload(Group.event),
                selectinload(AttendanceRecord.runner),
                selectinload(AttendanceRecord.result),
            )
        )
        if record is None or (
            user.role != UserRole.admin and record.group.event.created_by != user.id
        ):
            return _fix_redirect(q, event_id, "Запись не найдена")
        changed = await _set_finish_status(session, record, FinishStatus.dnf, user)
        await session.commit()
    return _fix_redirect(
        q, event_id, "Статус изменён на DNF, бегун уведомлён" if changed else "Уже DNF"
    )


@router.post("/results/fix/{record_id}/unset-dnf", response_model=None)
async def results_fix_unset_dnf(
    request: Request, record_id: int, q: str = Form(""), event_id: str = Form("")
) -> RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    if StaffPermission.results_review not in user.granted_permissions:
        return RedirectResponse("/admin-tools", status_code=303)
    async with SessionLocal() as session:
        record = await session.scalar(
            select(AttendanceRecord)
            .where(AttendanceRecord.id == record_id)
            .options(
                selectinload(AttendanceRecord.group).selectinload(Group.event),
                selectinload(AttendanceRecord.runner),
                selectinload(AttendanceRecord.result),
            )
        )
        if record is None or (
            user.role != UserRole.admin and record.group.event.created_by != user.id
        ):
            return _fix_redirect(q, event_id, "Запись не найдена")
        changed = await _set_finish_status(session, record, FinishStatus.finished, user)
        await session.commit()
    return _fix_redirect(
        q, event_id, "Статус возвращён на финиш, бегун уведомлён" if changed else "Уже финиш"
    )
