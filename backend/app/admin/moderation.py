from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.admin.tools_common import get_tools_user, login_redirect, templates
from app.core.db import SessionLocal
from app.models.attendance import AttendanceRecord
from app.models.enums import UserRole
from app.models.event import Event
from app.models.user import User
from app.services.csv_import_service import import_attendance_csv

router = APIRouter(prefix="/admin-tools", tags=["admin-moderation"], include_in_schema=False)


async def _require_admin(request: Request) -> User | None:
    """CSV import/moderation/runner search are Admin-only per CLAUDE.md, even
    though the rest of admin-tools is also open to organizers."""
    user = await get_tools_user(request)
    if user is None or user.role != UserRole.admin:
        return None
    return user


@router.get("/import", response_class=HTMLResponse, response_model=None)
async def import_page(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        events = list(
            await session.scalars(
                select(Event).options(selectinload(Event.groups)).order_by(Event.date.desc())
            )
        )
    return templates.TemplateResponse(
        request,
        "import.html",
        {
            "active": "import",
            "tools_user": user,
            "events": events,
            "selected_group_id": None,
            "result": None,
        },
    )


@router.post("/import", response_class=HTMLResponse, response_model=None)
async def import_submit(
    request: Request, group_id: int = Form(...), file: UploadFile | None = None
) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()

    flash_error = None
    result = None
    async with SessionLocal() as session:
        if file is None or not file.filename:
            flash_error = "Выберите CSV-файл"
        else:
            content = await file.read()
            try:
                result = await import_attendance_csv(session, group_id, content)
                await session.commit()
            except ValueError as exc:
                flash_error = str(exc)

        events = list(
            await session.scalars(
                select(Event).options(selectinload(Event.groups)).order_by(Event.date.desc())
            )
        )

    return templates.TemplateResponse(
        request,
        "import.html",
        {
            "active": "import",
            "tools_user": user,
            "events": events,
            "selected_group_id": group_id,
            "result": result,
            "flash_error": flash_error,
        },
    )


@router.get("/moderation", response_class=HTMLResponse, response_model=None)
async def moderation_page(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()

    search_for_raw = request.query_params.get("for")
    search_for = int(search_for_raw) if search_for_raw and search_for_raw.isdigit() else None
    q = request.query_params.get("q", "").strip()

    async with SessionLocal() as session:
        records = list(
            await session.scalars(
                select(AttendanceRecord)
                .where(AttendanceRecord.runner_id.is_(None))
                .options(selectinload(AttendanceRecord.group))
                .order_by(AttendanceRecord.id.desc())
            )
        )

        # Auto-suggest: exact (case-insensitive) email match against a registered account.
        emails = {r.raw_email.strip().lower() for r in records if r.raw_email}
        suggestions: dict[int, User] = {}
        if emails:
            matches = list(
                await session.scalars(select(User).where(func.lower(User.email).in_(emails)))
            )
            by_email = {u.email.lower(): u for u in matches}
            for r in records:
                if r.raw_email and r.raw_email.strip().lower() in by_email:
                    suggestions[r.id] = by_email[r.raw_email.strip().lower()]

        search_results: list[User] = []
        if search_for is not None and q:
            like = f"%{q}%"
            search_results = list(
                await session.scalars(
                    select(User)
                    .where(
                        or_(
                            User.first_name.ilike(like),
                            User.last_name.ilike(like),
                            User.email.ilike(like),
                        )
                    )
                    .order_by(User.id)
                    .limit(10)
                )
            )

    flash = request.query_params.get("flash")
    return templates.TemplateResponse(
        request,
        "moderation.html",
        {
            "active": "moderation",
            "tools_user": user,
            "records": records,
            "suggestions": suggestions,
            "search_for": search_for,
            "search_results": search_results,
            "q": q,
            "flash": flash,
        },
    )


@router.post("/moderation/match", response_model=None)
async def moderation_match(
    request: Request,
    attendance_id: int = Form(...),
    runner_id: int = Form(...),
) -> RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        record = await session.get(AttendanceRecord, attendance_id)
        runner = await session.get(User, runner_id)
        if record is None or runner is None:
            msg = "Match failed: record or runner not found"
        else:
            record.runner_id = runner.id
            await session.commit()
            msg = f"Привязано: «{record.raw_name}» → {runner.first_name} {runner.last_name}"
    return RedirectResponse(f"/admin-tools/moderation?flash={msg}", status_code=303)


@router.get("/runners", response_class=HTMLResponse, response_model=None)
async def runners_lookup(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    q = request.query_params.get("q", "").strip()
    async with SessionLocal() as session:
        stmt = select(User).order_by(User.id).limit(100)
        if q:
            like = f"%{q}%"
            stmt = (
                select(User)
                .where(
                    or_(
                        User.first_name.ilike(like),
                        User.last_name.ilike(like),
                        User.email.ilike(like),
                    )
                )
                .limit(100)
            )
        users = list(await session.scalars(stmt))
    return templates.TemplateResponse(
        request, "runners.html", {"active": "runners", "tools_user": user, "users": users, "q": q}
    )
