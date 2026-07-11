from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.models.attendance import AttendanceRecord
from app.models.enums import ResultSource, UserRole
from app.models.group import Group
from app.models.result import Result
from app.schemas.result import ResultOut
from app.services.fit_service import parse_fit
from app.services.gpx_service import TrackParseError, parse_gpx
from app.services.media_service import (
    FileTooLargeError,
    InvalidFileTypeError,
    delete_media,
    save_track_file,
)
from app.services.result_validation_service import validate_result
from app.services.track_types import ParsedTrack

router = APIRouter(tags=["results"])


async def _load_record(session: SessionDep, attendance_id: int) -> AttendanceRecord:
    record = await session.get(AttendanceRecord, attendance_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attendance record not found")
    return record


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
    if record.runner_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Attendance record is not yet matched to an account",
        )
    if user.role != UserRole.admin and record.runner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your result")

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

    if parsed.distance_km <= 0 or parsed.duration_seconds <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Result has no distance or duration")

    outcome = validate_result(
        distance_km=parsed.distance_km,
        target_distance_km=group.target_distance_km,
        source=source,
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

    result.distance_km = parsed.distance_km
    result.duration_seconds = parsed.duration_seconds
    result.pace_seconds_per_km = parsed.pace_seconds_per_km
    result.start_time = parsed.start_time
    result.source = source
    result.source_file = source_file_path
    result.track_points = parsed.track_points or None
    result.elevation_profile = parsed.elevation_profile or None
    result.telemetry = parsed.telemetry
    result.finish_status = outcome.finish_status
    result.status = outcome.moderation_status

    # finish_status on the attendance record is recomputed from the result.
    record.finish_status = outcome.finish_status

    await session.commit()
    await session.refresh(result)
    return result


@router.get("/attendance/{attendance_id}/result", response_model=ResultOut)
async def get_result(attendance_id: int, session: SessionDep) -> Result:
    result = await session.scalar(
        select(Result).where(Result.attendance_record_id == attendance_id)
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No result for this record")
    return result
