from datetime import date as date_type
from urllib.parse import quote

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.admin.tools_common import can_manage_event, login_redirect, require_permission, templates
from app.core.db import SessionLocal
from app.models.enums import StaffPermission, UserRole
from app.models.event import Event
from app.services import export_service, xlsx_service

router = APIRouter(prefix="/admin-tools", tags=["admin-tools"], include_in_schema=False)

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_response(data: bytes, filename: str) -> Response:
    # filename= carries an ASCII fallback (old clients), filename*= the real
    # UTF-8 name (event titles are routinely Cyrillic) per RFC 5987/6266.
    ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "report.xlsx"
    return Response(
        content=data,
        media_type=_XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
            )
        },
    )


def _parse_date(value: str | None) -> date_type | None:
    if not value:
        return None
    try:
        return date_type.fromisoformat(value)
    except ValueError:
        return None


@router.get("/reports", response_class=HTMLResponse, response_model=None)
async def reports_page(request: Request) -> HTMLResponse | RedirectResponse:
    user = await require_permission(request, StaffPermission.reports)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        stmt = select(Event).order_by(Event.date.desc())
        if user.role != UserRole.admin:
            stmt = stmt.where(Event.created_by == user.id)
        events = list(await session.scalars(stmt))
    return templates.TemplateResponse(
        request,
        "reports.html",
        {
            "active": "reports",
            "tools_user": user,
            "events": events,
            "is_admin": user.role == UserRole.admin,
        },
    )


@router.get("/reports/protocol/{event_id}", response_model=None)
async def event_protocol_report(request: Request, event_id: int) -> Response | RedirectResponse:
    user = await require_permission(request, StaffPermission.reports)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        event = await session.get(Event, event_id)
        if event is None or not can_manage_event(user, event):
            return RedirectResponse("/admin-tools/reports", status_code=303)
        rows = await export_service.build_event_protocol(session, event)
    data = xlsx_service.event_protocol_workbook(event.title, event.date.strftime("%d.%m.%Y"), rows)
    return _xlsx_response(data, f"Протокол {event.title} {event.date.isoformat()}.xlsx")


@router.get("/reports/results", response_model=None)
async def results_list_report(request: Request) -> Response | RedirectResponse:
    user = await require_permission(request, StaffPermission.reports)
    if user is None:
        return login_redirect()
    params = request.query_params
    event_id = int(params["event_id"]) if params.get("event_id") else None
    date_from = _parse_date(params.get("date_from"))
    date_to = _parse_date(params.get("date_to"))

    async with SessionLocal() as session:
        if event_id is not None:
            event = await session.get(Event, event_id)
            if event is None or not can_manage_event(user, event):
                return RedirectResponse("/admin-tools/reports", status_code=303)
        rows = await export_service.build_results_list(
            session,
            created_by=None if user.role == UserRole.admin else user.id,
            event_id=event_id,
            date_from=date_from,
            date_to=date_to,
        )
    title_bits = ["Результаты"]
    if date_from:
        title_bits.append(f"с {date_from.isoformat()}")
    if date_to:
        title_bits.append(f"по {date_to.isoformat()}")
    data = xlsx_service.results_list_workbook(" ".join(title_bits), rows)
    return _xlsx_response(data, f"{' '.join(title_bits)}.xlsx")


@router.get("/reports/summary", response_model=None)
async def summary_report(request: Request) -> Response | RedirectResponse:
    user = await require_permission(request, StaffPermission.reports)
    if user is None:
        return login_redirect()
    if user.role != UserRole.admin:
        # Platform-wide totals, not scoped to one organizer's events — unlike
        # the protocol/results exports above, this one stays admin-only
        # regardless of the reports permission.
        return RedirectResponse("/admin-tools/reports", status_code=303)
    async with SessionLocal() as session:
        stats = await export_service.build_summary(session)
    data = xlsx_service.summary_workbook("Сводная статистика DX", stats)
    return _xlsx_response(data, f"Сводка {stats.generated_at.date().isoformat()}.xlsx")
