import re

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app.admin.tools_common import (
    can_manage_event,
    combine_event_date_and_time,
    get_tools_user,
    login_redirect,
    templates,
)
from app.core.db import SessionLocal
from app.models.event import Event
from app.models.group import Group
from app.services.gpx_service import TrackParseError, parse_gpx
from app.services.group_service import set_group_route_gpx
from app.services.media_service import (
    FileTooLargeError,
    InvalidFileTypeError,
    delete_media,
    save_track_file,
)

router = APIRouter(prefix="/admin-tools", tags=["admin-tools"], include_in_schema=False)

_TRAILING_GROUP_NUMBER = re.compile(r"^(.*#)(\d+)$")


def _next_group_name(name: str) -> str:
    """"X-33 группа #1" -> "X-33 группа #2"; falls back to a "(копия)" suffix
    for names that don't end in a #N group number."""
    m = _TRAILING_GROUP_NUMBER.match(name)
    if m:
        return f"{m.group(1)}{int(m.group(2)) + 1}"
    return f"{name} (копия)"


@router.get(
    "/events/{event_id}/groups/new", response_class=HTMLResponse, response_model=None
)
async def group_new_form(request: Request, event_id: int) -> HTMLResponse | RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        event = await session.get(Event, event_id)
        if event is None or not can_manage_event(user, event):
            return RedirectResponse("/admin-tools/events", status_code=303)
    return templates.TemplateResponse(
        request,
        "group_form.html",
        {"active": "events", "tools_user": user, "event": event, "group": None},
    )


@router.post("/events/{event_id}/groups/new", response_model=None)
async def group_new_submit(
    request: Request,
    event_id: int,
    name: str = Form(...),
    location: str = Form(...),
    distance_code: str = Form(""),
    target_distance_km: float = Form(...),
    pace_min: str = Form(""),
    pace_max: str = Form(""),
    start_time: str = Form(""),
    counts_toward_rating: bool = Form(False),
) -> RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        event = await session.get(Event, event_id)
        if event is None or not can_manage_event(user, event):
            return RedirectResponse("/admin-tools/events", status_code=303)
        group = Group(
            event_id=event_id,
            name=name,
            location=location,
            distance_code=distance_code or None,
            target_distance_km=target_distance_km,
            pace_min=pace_min or None,
            pace_max=pace_max or None,
            start_time=combine_event_date_and_time(event.date, start_time),
            counts_toward_rating=counts_toward_rating,
        )
        session.add(group)
        await session.commit()
        await session.refresh(group)
    return RedirectResponse(f"/admin-tools/groups/{group.id}/edit?flash=Группа создана", 303)


@router.get("/groups/{group_id}/edit", response_class=HTMLResponse, response_model=None)
async def group_edit_form(request: Request, group_id: int) -> HTMLResponse | RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        group = await session.get(Group, group_id)
        if group is None:
            return RedirectResponse("/admin-tools/events", status_code=303)
        event = await session.get(Event, group.event_id)
        if event is None or not can_manage_event(user, event):
            return RedirectResponse("/admin-tools/events", status_code=303)
    flash = request.query_params.get("flash")
    return templates.TemplateResponse(
        request,
        "group_form.html",
        {
            "active": "events",
            "tools_user": user,
            "event": event,
            "group": group,
            "flash": flash,
        },
    )


@router.post("/groups/{group_id}/edit", response_model=None)
async def group_edit_submit(
    request: Request,
    group_id: int,
    name: str = Form(...),
    location: str = Form(...),
    distance_code: str = Form(""),
    target_distance_km: float = Form(...),
    pace_min: str = Form(""),
    pace_max: str = Form(""),
    start_time: str = Form(""),
    counts_toward_rating: bool = Form(False),
) -> RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        group = await session.get(Group, group_id)
        if group is None:
            return RedirectResponse("/admin-tools/events", status_code=303)
        event = await session.get(Event, group.event_id)
        if event is None or not can_manage_event(user, event):
            return RedirectResponse("/admin-tools/events", status_code=303)
        group.name = name
        group.location = location
        group.distance_code = distance_code or None
        group.target_distance_km = target_distance_km
        group.pace_min = pace_min or None
        group.pace_max = pace_max or None
        group.start_time = combine_event_date_and_time(event.date, start_time)
        group.counts_toward_rating = counts_toward_rating
        await session.commit()
    return RedirectResponse(f"/admin-tools/groups/{group_id}/edit?flash=Сохранено", 303)


@router.post("/groups/{group_id}/duplicate", response_model=None)
async def group_duplicate(request: Request, group_id: int) -> RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        group = await session.get(Group, group_id)
        if group is None:
            return RedirectResponse("/admin-tools/events", status_code=303)
        event = await session.get(Event, group.event_id)
        if event is None or not can_manage_event(user, event):
            return RedirectResponse("/admin-tools/events", status_code=303)
        copy = Group(
            event_id=group.event_id,
            name=_next_group_name(group.name),
            location=group.location,
            distance_code=group.distance_code,
            target_distance_km=group.target_distance_km,
            pace_min=group.pace_min,
            pace_max=group.pace_max,
            start_time=group.start_time,
            route_gpx=group.route_gpx,
            counts_toward_rating=group.counts_toward_rating,
        )
        session.add(copy)
        await session.commit()
        await session.refresh(copy)
    flash = "Группа продублирована — поправь название и время"
    return RedirectResponse(f"/admin-tools/groups/{copy.id}/edit?flash={flash}", 303)


@router.post("/groups/{group_id}/gpx", response_model=None)
async def group_gpx_upload(request: Request, group_id: int, file: UploadFile) -> RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        group = await session.get(Group, group_id)
        if group is None:
            return RedirectResponse("/admin-tools/events", status_code=303)
        event = await session.get(Event, group.event_id)
        if event is None or not can_manage_event(user, event):
            return RedirectResponse("/admin-tools/events", status_code=303)

        try:
            path, content, ext = await save_track_file(file, "routes")
        except (FileTooLargeError, InvalidFileTypeError) as exc:
            return RedirectResponse(f"/admin-tools/groups/{group_id}/edit?flash_error={exc}", 303)
        if ext != ".gpx":
            return RedirectResponse(
                f"/admin-tools/groups/{group_id}/edit?flash_error=Нужен .gpx файл", 303
            )
        try:
            parse_gpx(content)
        except TrackParseError as exc:
            delete_media(path)
            return RedirectResponse(f"/admin-tools/groups/{group_id}/edit?flash_error={exc}", 303)

        await set_group_route_gpx(session, group, path)
        await session.commit()
    return RedirectResponse(f"/admin-tools/groups/{group_id}/edit?flash=Маршрут загружен", 303)
