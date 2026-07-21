from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.models.attendance import AttendanceRecord
from app.models.enums import ModerationStatus, ResultSource, UserRole
from app.models.group import Group
from app.models.result import Result
from app.schemas.result import ImportUrlRequest, ResultOut
from app.services.fit_service import parse_fit
from app.services.gpx_service import TrackParseError, parse_gpx
from app.services.media_service import (
    FileTooLargeError,
    InvalidFileTypeError,
    delete_media,
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


async def _save_result(
    session: SessionDep,
    record: AttendanceRecord,
    group: Group,
    parsed: ParsedTrack,
    source: ResultSource,
    source_file_path: str | None,
) -> Result:
    """Shared by file upload, manual entry, and URL import: validate the parsed
    track, auto-check it against the group's target, and upsert the 1:1 Result."""
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

    result.distance_km = outcome.distance_km
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
        parsed = ParsedTrack(
            distance_km=distance_km,
            duration_seconds=duration_seconds,
            start_time=start_time,
        )
        source = ResultSource.manual

    return await _save_result(session, record, group, parsed, source, source_file_path)


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


@router.get("/attendance/{attendance_id}/result", response_model=ResultOut)
async def get_result(attendance_id: int, session: SessionDep) -> Result:
    result = await session.scalar(
        select(Result).where(Result.attendance_record_id == attendance_id)
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No result for this record")
    return result
