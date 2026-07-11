from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import OrganizerUser, SessionDep
from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, ModerationStatus, UserRole
from app.models.event import Event
from app.models.group import Group
from app.models.user import User
from app.schemas.group import (
    GroupCreate,
    GroupOut,
    GroupUpdate,
    Protocol,
    ProtocolEntry,
    RouteMap,
)
from app.services.gpx_service import TrackParseError, parse_gpx
from app.services.media_service import (
    FileTooLargeError,
    InvalidFileTypeError,
    delete_media,
    save_track_file,
)

router = APIRouter(tags=["groups"])


async def _get_group_or_404(session: SessionDep, group_id: int) -> Group:
    group = await session.get(Group, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
    return group


async def _assert_can_manage_group(session: SessionDep, group: Group, user: User) -> None:
    if user.role == UserRole.admin:
        return
    event = await session.get(Event, group.event_id)
    if event is None or event.created_by != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not manage this event")


@router.get("/events/{event_id}/groups", response_model=list[GroupOut])
async def list_groups(event_id: int, session: SessionDep) -> list[Group]:
    groups = await session.scalars(
        select(Group).where(Group.event_id == event_id).order_by(Group.id)
    )
    return list(groups)


@router.post(
    "/events/{event_id}/groups", response_model=GroupOut, status_code=status.HTTP_201_CREATED
)
async def create_group(
    event_id: int, payload: GroupCreate, user: OrganizerUser, session: SessionDep
) -> Group:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    if user.role != UserRole.admin and event.created_by != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not manage this event")

    group = Group(event_id=event_id, **payload.model_dump())
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


@router.get("/groups/{group_id}", response_model=GroupOut)
async def get_group(group_id: int, session: SessionDep) -> Group:
    return await _get_group_or_404(session, group_id)


@router.patch("/groups/{group_id}", response_model=GroupOut)
async def update_group(
    group_id: int, payload: GroupUpdate, user: OrganizerUser, session: SessionDep
) -> Group:
    group = await _get_group_or_404(session, group_id)
    await _assert_can_manage_group(session, group, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(group, field, value)
    await session.commit()
    await session.refresh(group)
    return group


@router.post("/groups/{group_id}/route-gpx", response_model=GroupOut)
async def upload_route_gpx(
    group_id: int, user: OrganizerUser, session: SessionDep, file: UploadFile
) -> Group:
    group = await _get_group_or_404(session, group_id)
    await _assert_can_manage_group(session, group, user)
    try:
        path, content, ext = await save_track_file(file, "routes")
    except (FileTooLargeError, InvalidFileTypeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if ext != ".gpx":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Route must be a .gpx file")
    try:
        parse_gpx(content)  # validate it parses before persisting the path
    except TrackParseError as exc:
        delete_media(path)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    delete_media(group.route_gpx)
    group.route_gpx = path
    await session.commit()
    await session.refresh(group)
    return group


@router.get("/groups/{group_id}/route-gpx")
async def download_route_gpx(group_id: int, session: SessionDep) -> FileResponse:
    group = await _get_group_or_404(session, group_id)
    if not group.route_gpx:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No route GPX for this group")
    from app.services.media_service import media_path_to_fs

    fs = media_path_to_fs(group.route_gpx)
    if not fs.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Route file unavailable")
    return FileResponse(
        fs, media_type="application/gpx+xml", filename=f"group-{group_id}-route.gpx"
    )


@router.get("/groups/{group_id}/route-map", response_model=RouteMap)
async def route_map(group_id: int, session: SessionDep) -> RouteMap:
    group = await _get_group_or_404(session, group_id)
    if not group.route_gpx:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No route GPX for this group")
    from app.services.media_service import media_path_to_fs

    fs = media_path_to_fs(group.route_gpx)
    try:
        with open(fs, "rb") as f:
            parsed = parse_gpx(f.read())
    except (FileNotFoundError, TrackParseError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Route file unavailable") from exc
    return RouteMap(
        track_points=parsed.track_points,
        elevation_profile=parsed.elevation_profile,
        distance_km=parsed.distance_km,
    )


@router.get("/groups/{group_id}/protocol", response_model=Protocol)
async def protocol(group_id: int, session: SessionDep) -> Protocol:
    await _get_group_or_404(session, group_id)
    scalar_records = await session.scalars(
        select(AttendanceRecord)
        .where(AttendanceRecord.group_id == group_id)
        .options(selectinload(AttendanceRecord.result), selectinload(AttendanceRecord.runner))
    )
    records = list(scalar_records)

    def to_entry(rec: AttendanceRecord) -> ProtocolEntry:
        res = rec.result
        # Once linked to an account, always show its *current* name — not the
        # raw_name frozen at CSV-import time. Otherwise a guest merged into a
        # real account (or matched under a differently-spelled CSV name) keeps
        # showing its old label and the protocol reads as two different people.
        display_name = (
            f"{rec.runner.first_name} {rec.runner.last_name}" if rec.runner else rec.raw_name
        )
        return ProtocolEntry(
            rank=None,
            attendance_id=rec.id,
            runner_id=rec.runner_id,
            display_name=display_name,
            distance_km=res.distance_km if res else None,
            duration_seconds=res.duration_seconds if res else None,
            pace_seconds_per_km=res.pace_seconds_per_km if res else None,
            finish_status=rec.finish_status.value,
            moderation_status=res.status.value if res else None,
        )

    # Finishers: approved + finished results, ranked by duration ascending.
    finishers = [
        rec
        for rec in records
        if rec.result
        and rec.result.status == ModerationStatus.approved
        and rec.result.finish_status == FinishStatus.finished
    ]
    finishers.sort(key=lambda r: r.result.duration_seconds)
    finisher_entries = []
    for i, rec in enumerate(finishers, start=1):
        entry = to_entry(rec)
        entry.rank = i
        finisher_entries.append(entry)

    finisher_ids = {rec.id for rec in finishers}
    dnf_entries = [
        to_entry(rec) for rec in records if rec.finish_status == FinishStatus.dnf
    ]
    # Everyone else who's on the list (from CSV import / auto-match / guest
    # creation) but doesn't have an approved+finished result yet — without this
    # bucket they'd be on the group but invisible in the protocol entirely.
    pending_entries = [
        to_entry(rec)
        for rec in records
        if rec.id not in finisher_ids and rec.finish_status != FinishStatus.dnf
    ]

    return Protocol(
        group_id=group_id,
        finishers=finisher_entries,
        pending=pending_entries,
        dnf=dnf_entries,
    )
