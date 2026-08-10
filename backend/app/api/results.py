from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.core.timezone import EVENT_TZ
from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, ModerationStatus, ResultSource, UserRole
from app.models.event import Event
from app.models.group import Group
from app.models.result import Result
from app.models.signup import Signup
from app.schemas.result import ImportUrlRequest, ResultOut
from app.services.fit_service import parse_fit
from app.services.gpx_service import TrackParseError, parse_gpx
from app.services.media_service import (
    FileTooLargeError,
    InvalidFileTypeError,
    delete_media,
    save_image,
    save_track_bytes,
    save_track_file,
)
from app.services.result_validation_service import validate_result
from app.services.safe_fetch import FetchError, detect_workout_format, fetch_external_workout_file
from app.services.track_types import ParsedTrack

router = APIRouter(tags=["results"])


async def _load_record(session: SessionDep, attendance_id: int) -> AttendanceRecord:
    record = await session.get(AttendanceRecord, attendance_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attendance record not found")
    return record


def _check_can_submit(user: CurrentUser, record: AttendanceRecord) -> None:
    if record.runner_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Attendance record is not yet matched to an account",
        )
    if user.role != UserRole.admin and record.runner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your result")


async def _check_no_pending_result(
    session: SessionDep, user: CurrentUser, record: AttendanceRecord
) -> None:
    """Once a result is sitting in the moderation queue, a runner can't just
    keep re-submitting attempts hoping one auto-validates — they wait for
    Admin's decision. Admin themselves can still overwrite at any time
    (e.g. fixing something directly instead of going through the queue)."""
    if user.role == UserRole.admin:
        return
    existing = await session.scalar(
        select(Result).where(Result.attendance_record_id == record.id)
    )
    if existing is not None and existing.status == ModerationStatus.pending:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Результат уже отправлен и ожидает проверки администратором — "
            "дождитесь решения, прежде чем загружать новый",
        )


def _require_manual_screenshot(user: CurrentUser, image: UploadFile | None) -> None:
    """A runner's manual entry has no track, so a screenshot (date/time of start,
    distance, run time, track visible) is the only evidence — required for them.
    Admins entering data by hand are trusted and exempt."""
    if user.role != UserRole.admin and (image is None or not image.filename):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "К ручному результату нужен скриншот, где видны дата и время старта, "
            "дистанция, время пробежки и трек.",
        )


async def _save_screenshot(image: UploadFile) -> str:
    try:
        return await save_image(image, "result_screenshots")
    except (FileTooLargeError, InvalidFileTypeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


async def _family_group_ids(session: SessionDep, group: Group) -> list[int]:
    """All groups sharing this group's distance_code (one shared protocol), or
    just this group when it has no code."""
    if group.distance_code:
        ids = await session.scalars(
            select(Group.id).where(
                Group.event_id == group.event_id,
                Group.distance_code == group.distance_code,
            )
        )
        return list(ids)
    return [group.id]


def _event_has_started(group: Group, event: Event) -> bool:
    now = datetime.now(EVENT_TZ)
    if group.start_time is not None:
        start = group.start_time
        if start.tzinfo is None:  # SQLite (tests) drops tzinfo — stored as UTC
            start = start.replace(tzinfo=UTC)
        return start <= now
    return event.date <= now.date()


async def _save_result(
    session: SessionDep,
    record: AttendanceRecord,
    group: Group,
    parsed: ParsedTrack,
    source: ResultSource,
    source_file_path: str | None,
    screenshot_path: str | None = None,
    update_screenshot: bool = False,
) -> Result:
    """Shared by file upload, manual entry, and URL import: validate the parsed
    track, auto-check it against the group's target, and upsert the 1:1 Result.

    `update_screenshot` toggles whether the screenshot is (re)written — a
    re-submission that doesn't carry a new image keeps the existing one."""
    if parsed.distance_km <= 0 or parsed.duration_seconds <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Result has no distance or duration")

    outcome = validate_result(
        distance_km=parsed.distance_km,
        duration_seconds=parsed.duration_seconds,
        target_distance_km=group.target_distance_km,
        source=source,
        protocol_finish_status=record.finish_status,
        result_start_time=parsed.start_time,
        group_start_time=group.start_time,
    )

    # 1:1 upsert — overwrite an existing result (and its stored file) in place.
    result = await session.scalar(
        select(Result).where(Result.attendance_record_id == record.id)
    )
    if result is not None:
        if result.source_file and result.source_file != source_file_path:
            delete_media(result.source_file)
    else:
        result = Result(attendance_record_id=record.id)
        session.add(result)

    if update_screenshot:
        if result.screenshot and result.screenshot != screenshot_path:
            delete_media(result.screenshot)
        result.screenshot = screenshot_path

    result.distance_km = outcome.distance_km
    # Keep the file's own measured distance so moderation can see what was
    # distrusted when distance_km falls back to the group target. Manual entries
    # have no independent measurement.
    result.measured_distance_km = (
        parsed.distance_km if source == ResultSource.file else None
    )
    result.duration_seconds = outcome.duration_seconds
    result.pace_seconds_per_km = outcome.pace_seconds_per_km
    result.start_time = parsed.start_time
    result.source = source
    result.source_file = source_file_path
    result.track_points = parsed.track_points or None
    result.elevation_profile = parsed.elevation_profile or None
    result.telemetry = parsed.telemetry
    result.finish_status = outcome.finish_status
    result.status = outcome.moderation_status

    # record.finish_status is never touched here — it's the protocol's source
    # of truth (set at CSV import), not something a Result upload overrides.
    # See validate_result's docstring for why.

    await session.commit()
    await session.refresh(result)
    return result


@router.post(
    "/attendance/{attendance_id}/result",
    response_model=ResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_result(
    attendance_id: int,
    user: CurrentUser,
    session: SessionDep,
    # Manual entry is sent as multipart form fields (not a JSON body) so a single
    # endpoint can branch between a file upload and manual data. File takes priority.
    file: UploadFile | None = None,
    # Optional screenshot (a photo of the watch/app screen) — evidence for a
    # manual entry that has no GPX/FIT track. Ignored when a track file is sent.
    image: UploadFile | None = None,
    distance_km: Annotated[float | None, Form()] = None,
    duration_seconds: Annotated[int | None, Form()] = None,
    start_time: Annotated[datetime | None, Form()] = None,
) -> Result:
    record = await _load_record(session, attendance_id)
    _check_can_submit(user, record)
    await _check_no_pending_result(session, user, record)

    group = await session.get(Group, record.group_id)
    assert group is not None

    source_file_path: str | None = None
    if file is not None and file.filename:
        # GPX/FIT upload is admin-only now — runners enter results manually.
        if user.role != UserRole.admin:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Загрузка GPX/FIT недоступна — введите результат вручную.",
            )
        try:
            path, content, ext = await save_track_file(file, "results")
        except (FileTooLargeError, InvalidFileTypeError) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        try:
            parsed = parse_gpx(content) if ext == ".gpx" else parse_fit(content)
        except TrackParseError as exc:
            delete_media(path)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        source = ResultSource.file
        source_file_path = path
    else:
        if distance_km is None or duration_seconds is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Manual entry requires distance_km and duration_seconds",
            )
        _require_manual_screenshot(user, image)
        parsed = ParsedTrack(
            distance_km=distance_km,
            duration_seconds=duration_seconds,
            start_time=start_time,
        )
        source = ResultSource.manual

    # A screenshot only makes sense as evidence for data with no track of its
    # own (manual entry) — skip it when a GPX/FIT file was uploaded.
    screenshot_path: str | None = None
    update_screenshot = False
    if source is ResultSource.manual and image is not None and image.filename:
        try:
            screenshot_path = await save_image(image, "result_screenshots")
        except (FileTooLargeError, InvalidFileTypeError) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        update_screenshot = True

    return await _save_result(
        session,
        record,
        group,
        parsed,
        source,
        source_file_path,
        screenshot_path=screenshot_path,
        update_screenshot=update_screenshot,
    )


@router.post(
    "/attendance/{attendance_id}/result/import-url",
    response_model=ResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def import_result_from_url(
    attendance_id: int,
    payload: ImportUrlRequest,
    user: CurrentUser,
    session: SessionDep,
) -> Result:
    """Alternative to uploading a file: fetch a GPX/FIT export link from a
    watch's own app (Suunto/Garmin/Coros etc — see safe_fetch for how the
    fetch is kept SSRF-safe) and treat it exactly like an uploaded file."""
    # URL import is admin-only now — runners enter results manually.
    if user.role != UserRole.admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Импорт по ссылке недоступен — введите результат вручную.",
        )
    record = await _load_record(session, attendance_id)
    _check_can_submit(user, record)
    await _check_no_pending_result(session, user, record)

    group = await session.get(Group, record.group_id)
    assert group is not None

    try:
        content, content_type, content_disposition = await fetch_external_workout_file(
            payload.url
        )
    except FetchError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    fmt = detect_workout_format(content, content_type, content_disposition)
    if fmt is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Could not recognize the file as GPX or FIT"
        )

    try:
        parsed = parse_gpx(content) if fmt == "gpx" else parse_fit(content)
    except TrackParseError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    try:
        source_file_path = save_track_bytes(content, f".{fmt}", "results")
    except (FileTooLargeError, InvalidFileTypeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return await _save_result(
        session, record, group, parsed, ResultSource.file, source_file_path
    )


@router.post(
    "/groups/{group_id}/result",
    response_model=ResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_group_result(
    group_id: int,
    user: CurrentUser,
    session: SessionDep,
    image: UploadFile | None = None,
    distance_km: Annotated[float | None, Form()] = None,
    duration_seconds: Annotated[int | None, Form()] = None,
    start_time: Annotated[datetime | None, Form()] = None,
) -> Result:
    """Self-report a result for a group you're signed up to, *before* the
    protocol (CSV) exists. Manual entry only, screenshot required. Creates a
    `self_reported` AttendanceRecord that a later CSV import merges into (so no
    duplicate in the shared protocol)."""
    group = await session.get(Group, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")

    signup = await session.scalar(
        select(Signup).where(
            Signup.event_id == group.event_id, Signup.runner_id == user.id
        )
    )
    if signup is None or signup.group_id != group_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Вы не записаны в эту группу")

    event = await session.get(Event, group.event_id)
    assert event is not None
    if not _event_has_started(group, event):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Загрузить результат можно только после старта группы.",
        )

    if distance_km is None or duration_seconds is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Укажите дистанцию и время.",
        )
    _require_manual_screenshot(user, image)

    # Reuse the runner's existing record in this distance family if any (e.g. a
    # re-submission), else create a self-reported one.
    family_ids = await _family_group_ids(session, group)
    record = await session.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.group_id.in_(family_ids),
            AttendanceRecord.runner_id == user.id,
        )
    )
    if record is None:
        record = AttendanceRecord(
            group_id=group.id,
            raw_name=f"{user.first_name} {user.last_name}",
            raw_email=user.email,
            runner_id=user.id,
            finish_status=FinishStatus.finished,
            self_reported=True,
        )
        session.add(record)
        await session.flush()

    await _check_no_pending_result(session, user, record)

    screenshot_path = (
        await _save_screenshot(image) if image is not None and image.filename else None
    )
    parsed = ParsedTrack(
        distance_km=distance_km, duration_seconds=duration_seconds, start_time=start_time
    )
    return await _save_result(
        session,
        record,
        group,
        parsed,
        ResultSource.manual,
        None,
        screenshot_path=screenshot_path,
        update_screenshot=screenshot_path is not None,
    )


@router.get("/attendance/{attendance_id}/result", response_model=ResultOut)
async def get_result(attendance_id: int, session: SessionDep) -> Result:
    result = await session.scalar(
        select(Result).where(Result.attendance_record_id == attendance_id)
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No result for this record")
    return result
