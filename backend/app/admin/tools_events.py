from datetime import UTC, datetime
from datetime import date as date_type

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.admin.tools_common import can_manage_event, get_tools_user, login_redirect, templates
from app.core.db import SessionLocal
from app.core.timezone import EVENT_TZ
from app.models.enums import UserRole
from app.models.event import Event, EventPhoto
from app.models.group import Group
from app.services.media_service import (
    FileTooLargeError,
    InvalidFileTypeError,
    delete_media,
    save_image,
    save_image_with_thumbnail,
)

router = APIRouter(prefix="/admin-tools", tags=["admin-tools"], include_in_schema=False)


@router.get("/events", response_class=HTMLResponse, response_model=None)
async def events_list(request: Request) -> HTMLResponse | RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        stmt = (
            select(Event).options(selectinload(Event.groups)).order_by(Event.date.desc())
        )
        if user.role != UserRole.admin:
            stmt = stmt.where(Event.created_by == user.id)
        events = list(await session.scalars(stmt))
    return templates.TemplateResponse(
        request,
        "events_list.html",
        {"active": "events", "tools_user": user, "events": events},
    )


@router.get("/events/new", response_class=HTMLResponse, response_model=None)
async def event_new_form(request: Request) -> HTMLResponse | RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    return templates.TemplateResponse(
        request, "event_form.html", {"active": "events", "tools_user": user, "event": None}
    )


@router.post("/events/new", response_model=None)
async def event_new_submit(
    request: Request,
    title: str = Form(...),
    date: date_type = Form(...),
    description: str = Form(""),
) -> RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        event = Event(title=title, date=date, description=description or None, created_by=user.id)
        session.add(event)
        await session.commit()
        await session.refresh(event)
    return RedirectResponse(f"/admin-tools/events/{event.id}/edit?flash=Событие создано", 303)


@router.get("/events/{event_id}/edit", response_class=HTMLResponse, response_model=None)
async def event_edit_form(request: Request, event_id: int) -> HTMLResponse | RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        event = await session.get(
            Event, event_id, options=[selectinload(Event.groups), selectinload(Event.photos)]
        )
        if event is None or not can_manage_event(user, event):
            return RedirectResponse("/admin-tools/events", status_code=303)
    flash = request.query_params.get("flash")
    return templates.TemplateResponse(
        request,
        "event_form.html",
        {"active": "events", "tools_user": user, "event": event, "flash": flash},
    )


@router.post("/events/{event_id}/edit", response_model=None)
async def event_edit_submit(
    request: Request,
    event_id: int,
    title: str = Form(...),
    date: date_type = Form(...),
    description: str = Form(""),
) -> RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        event = await session.get(Event, event_id)
        if event is None or not can_manage_event(user, event):
            return RedirectResponse("/admin-tools/events", status_code=303)
        event.title = title
        event.description = description or None
        if event.date != date:
            event.date = date
            # A group's start_time always falls on its event's date (see
            # combine_event_date_and_time) — moving the event carries every
            # group's Cheboksary-local time-of-day along to the new date
            # instead of leaving them pointing at the old one. Convert to
            # local before re-combining, or the UTC-stored time-of-day would
            # drift by the timezone offset each time an event moves.
            groups = await session.scalars(select(Group).where(Group.event_id == event.id))
            for group in groups:
                if group.start_time is not None:
                    local_time = group.start_time.astimezone(EVENT_TZ).time()
                    local_dt = datetime.combine(date, local_time, tzinfo=EVENT_TZ)
                    group.start_time = local_dt.astimezone(UTC)
        await session.commit()
    return RedirectResponse(f"/admin-tools/events/{event_id}/edit?flash=Сохранено", 303)


@router.post("/events/{event_id}/cover", response_model=None)
async def event_cover_upload(
    request: Request, event_id: int, file: UploadFile
) -> RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        event = await session.get(Event, event_id)
        if event is None or not can_manage_event(user, event):
            return RedirectResponse("/admin-tools/events", status_code=303)
        try:
            path = await save_image(file, "covers")
        except (FileTooLargeError, InvalidFileTypeError) as exc:
            return RedirectResponse(
                f"/admin-tools/events/{event_id}/edit?flash_error={exc}", 303
            )
        delete_media(event.cover_image)
        event.cover_image = path
        await session.commit()
    return RedirectResponse(f"/admin-tools/events/{event_id}/edit?flash=Обложка обновлена", 303)


@router.post("/events/{event_id}/photos", response_model=None)
async def event_photo_upload(
    request: Request, event_id: int, files: list[UploadFile]
) -> RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        event = await session.get(Event, event_id)
        if event is None or not can_manage_event(user, event):
            return RedirectResponse("/admin-tools/events", status_code=303)
        for file in files:
            if not file.filename:
                continue
            try:
                path, thumb_path = await save_image_with_thumbnail(file, "photos")
            except (FileTooLargeError, InvalidFileTypeError) as exc:
                return RedirectResponse(
                    f"/admin-tools/events/{event_id}/edit?flash_error={file.filename}: {exc}",
                    303,
                )
            session.add(
                EventPhoto(event_id=event.id, image=path, thumbnail=thumb_path, uploaded_by=user.id)
            )
        await session.commit()
    return RedirectResponse(f"/admin-tools/events/{event_id}/edit?flash=Фото добавлены", 303)
