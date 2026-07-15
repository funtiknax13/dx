from fastapi import APIRouter, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import AdminUser, SessionDep
from app.models.attendance import AttendanceRecord
from app.models.event import Event
from app.models.user import User
from app.schemas.attendance import (
    AttendanceOut,
    CsvImportResponse,
    MatchRequest,
    UnmatchedRecord,
)
from app.services.csv_import_service import import_attendance_csv

router = APIRouter(tags=["attendance"])


@router.post(
    "/events/{event_id}/attendance/import-csv",
    response_model=CsvImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_csv(
    event_id: int, _admin: AdminUser, session: SessionDep, file: UploadFile
) -> CsvImportResponse:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    content = await file.read()
    try:
        result = await import_attendance_csv(session, event_id, content)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return CsvImportResponse(
        created=result.created_count,
        skipped_duplicates=result.skipped_duplicates,
        skipped_empty=result.skipped_empty,
        skipped_no_tag=result.skipped_no_tag,
        skipped_unmatched_tag=result.skipped_unmatched_tag,
        fallback_used=result.fallback_used,
    )


@router.get("/attendance/unmatched", response_model=list[UnmatchedRecord])
async def unmatched(_admin: AdminUser, session: SessionDep) -> list[AttendanceRecord]:
    records = await session.scalars(
        select(AttendanceRecord)
        .where(AttendanceRecord.runner_id.is_(None))
        .order_by(AttendanceRecord.id.desc())
    )
    return list(records)


@router.post("/attendance/{attendance_id}/match", response_model=AttendanceOut)
async def match(
    attendance_id: int, payload: MatchRequest, _admin: AdminUser, session: SessionDep
) -> AttendanceRecord:
    record = await session.get(AttendanceRecord, attendance_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attendance record not found")
    runner = await session.get(User, payload.runner_id)
    if runner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Runner not found")

    record.runner_id = runner.id
    await session.commit()
    await session.refresh(record)
    return record
