from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, ModerationStatus, ResultSource, UserRole
from app.models.event import Event
from app.models.group import Group
from app.models.result import Result
from app.models.signup import Signup
from app.schemas.result import GroupParticipationOut, ImportUrlRequest, ResultOut
from app.services.event_time import group_has_started
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
from app.services.participation_service import get_group_participation
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


async def _check_resubmit_allowed(
    session: SessionDep, user: CurrentUser, record: AttendanceRecord
) -> None:
    """A runner can (re)upload only when there's nothing to wait on and nothing
    final: a *pending* result is still in the moderation queue, and an *approved*
    one is settled — both block a new upload. A *rejected* result (or no result
    yet) can be replaced, so the runner can fix the problem and resubmit. Admin is
    never blocked (they can overwrite directly instead of going via the queue)."""
    if user.role == UserRole.admin:
        return
    existing = await session.scalar(select(Result).where(Result.attendance_record_id == record.id))
    if existing is None:
        return
    if existing.status == ModerationStatus.pending:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Результат уже отправлен и ожидает проверки администратором — "
            "дождитесь решения, прежде чем загружать новый",
        )
    if existing.status == ModerationStatus.approved:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Результат уже подтверждён — повторная загрузка недоступна.",
        )


def _real_images(images: list[UploadFile]) -> list[UploadFile]:
    """Browsers can submit an empty file part for an untouched <input>; keep only
    parts that actually carry a file."""
    return [img for img in images if img.filename]


def _clean_comment(comment: str | None) -> str | None:
    """Trim, drop if empty, and cap at the column length (1000)."""
    cleaned = (comment or "").strip()
    return cleaned[:1000] or None


def _require_manual_screenshot(user: CurrentUser, images: list[UploadFile]) -> None:
    """A runner's manual entry has no track, so a screenshot (date/time of start,
    distance, run time, track visible) is the only evidence — at least one is
    required for them. They may attach several when one screen can't show it all.
    Admins entering data by hand are trusted and exempt."""
    if user.role != UserRole.admin and not _real_images(images):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "К ручному результату нужен хотя бы один скриншот, где видны дата и время "
            "старта, дистанция, время пробежки и трек.",
        )


# Faster than this is not a real running pace for any distance on offer here —
# it almost always means the H:MM:SS field was misread as M:SS (e.g. "2:05"
# typed meaning 2h05m, parsed as 2m05s). Backend-side backstop for the same
# check the manual-entry form already runs client-side; no admin exemption —
# entering data by hand on someone else's behalf is just as typo-prone.
MIN_MANUAL_PACE_SECONDS_PER_KM = 90


def _require_plausible_pace(distance_km: float, duration_seconds: int) -> None:
    if distance_km > 0 and duration_seconds / distance_km < MIN_MANUAL_PACE_SECONDS_PER_KM:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Время указано некорректно — проверьте формат Ч:ММ:СС "
            "(например, 2 часа 5 минут — это 2:05:00, а не 2:05).",
        )


async def _save_screenshots(images: list[UploadFile]) -> list[str]:
    paths: list[str] = []
    try:
        for img in _real_images(images):
            paths.append(await save_image(img, "result_screenshots"))
    except (FileTooLargeError, InvalidFileTypeError) as exc:
        for path in paths:  # don't leak the ones already written
            delete_media(path)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return paths


async def _save_result(
    session: SessionDep,
    record: AttendanceRecord,
    group: Group,
    parsed: ParsedTrack,
    source: ResultSource,
    source_file_path: str | None,
    screenshots: list[str] | None = None,
    update_screenshots: bool = False,
    comment: str | None = None,
) -> Result:
    """Shared by file upload, manual entry, and URL import: validate the parsed
    track, auto-check it against the group's target, and upsert the 1:1 Result.

    `update_screenshots` toggles whether the screenshots are (re)written — a
    re-submission that doesn't carry new images keeps the existing ones."""
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
    result = await session.scalar(select(Result).where(Result.attendance_record_id == record.id))
    if result is not None:
        if result.source_file and result.source_file != source_file_path:
            delete_media(result.source_file)
    else:
        result = Result(attendance_record_id=record.id)
        session.add(result)

    if update_screenshots:
        new = screenshots or []
        for old in result.screenshots or []:
            if old not in new:
                delete_media(old)
        result.screenshots = new or None

    result.comment = comment
    result.distance_km = outcome.distance_km
    # Keep the file's own measured distance so moderation can see what was
    # distrusted when distance_km falls back to the group target. Manual entries
    # have no independent measurement.
    result.measured_distance_km = parsed.distance_km if source == ResultSource.file else None
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
    # Optional screenshots (photos of the watch/app screen) — evidence for a
    # manual entry that has no GPX/FIT track. Several are allowed when one screen
    # can't show it all. Ignored when a track file is sent.
    images: list[UploadFile] = [],  # noqa: B006 — FastAPI reads the default, never mutates it
    distance_km: Annotated[float | None, Form()] = None,
    duration_seconds: Annotated[int | None, Form()] = None,
    start_time: Annotated[datetime | None, Form()] = None,
    # Optional note explaining a mismatch with the group (GPS dropped, ran to the
    # start from home, …) — carried into the Result for the moderator to see.
    comment: Annotated[str | None, Form()] = None,
) -> Result:
    record = await _load_record(session, attendance_id)
    _check_can_submit(user, record)
    await _check_resubmit_allowed(session, user, record)

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
        _require_manual_screenshot(user, images)
        _require_plausible_pace(distance_km, duration_seconds)
        parsed = ParsedTrack(
            distance_km=distance_km,
            duration_seconds=duration_seconds,
            start_time=start_time,
        )
        source = ResultSource.manual

    # Screenshots only make sense as evidence for data with no track of its
    # own (manual entry) — skip them when a GPX/FIT file was uploaded.
    screenshots: list[str] | None = None
    update_screenshots = False
    if source is ResultSource.manual and _real_images(images):
        screenshots = await _save_screenshots(images)
        update_screenshots = True

    return await _save_result(
        session,
        record,
        group,
        parsed,
        source,
        source_file_path,
        screenshots=screenshots,
        update_screenshots=update_screenshots,
        comment=_clean_comment(comment),
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
    await _check_resubmit_allowed(session, user, record)

    group = await session.get(Group, record.group_id)
    assert group is not None

    try:
        content, content_type, content_disposition = await fetch_external_workout_file(payload.url)
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

    return await _save_result(session, record, group, parsed, ResultSource.file, source_file_path)


@router.post(
    "/groups/{group_id}/result",
    response_model=ResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_group_result(
    group_id: int,
    user: CurrentUser,
    session: SessionDep,
    images: list[UploadFile] = [],  # noqa: B006 — FastAPI reads the default, never mutates it
    distance_km: Annotated[float | None, Form()] = None,
    duration_seconds: Annotated[int | None, Form()] = None,
    start_time: Annotated[datetime | None, Form()] = None,
    comment: Annotated[str | None, Form()] = None,
) -> Result:
    """Self-report a result for a group — no signup needed (a runner who forgot
    to sign up still ran), only that the group has started. Manual entry only,
    screenshot required, and it always lands in the moderation queue. Creates a
    `self_reported` AttendanceRecord that a later CSV import merges into (so no
    duplicate in the shared protocol); until an admin approves the result the
    run stays out of the public protocol, profile history and every stat."""
    group = await session.get(Group, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")

    event = await session.get(Event, group.event_id)
    assert event is not None
    if not group_has_started(group.start_time, event.date):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Загрузить результат можно только после старта группы.",
        )

    if distance_km is None or duration_seconds is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Укажите дистанцию и время.",
        )
    _require_manual_screenshot(user, images)
    _require_plausible_pace(distance_km, duration_seconds)

    # Reuse the runner's existing record in this distance family if any (e.g. a
    # CSV-placed one that has no result yet, or a re-submission), else create a
    # self-reported one.
    participation = await get_group_participation(session, user.id, group)
    if participation.other_group is not None:
        # One group per runner per event — a second record in another group
        # would put them in two protocols at once.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"В этом событии у вас уже есть результат в группе «{participation.other_group.name}». "
            "Если он записан не в ту группу — напишите в поддержку.",
        )
    record = participation.record
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
    elif record.group_id != group.id:
        # A rejected record from a *different* group's family, reused here —
        # move it rather than leave it pointing at the group it was turned
        # down for (see get_group_participation).
        record.group_id = group.id

    await _check_resubmit_allowed(session, user, record)

    # A signup is intent, the run is the fact: someone who signed up for D-21 and
    # ran X-34 has their signup follow the run, so the roster and their "upload a
    # result" list don't keep a stale entry for the group they didn't run in.
    signup = await session.scalar(
        select(Signup).where(Signup.event_id == group.event_id, Signup.runner_id == user.id)
    )
    if signup is not None and signup.group_id != record.group_id:
        signup.group_id = record.group_id

    screenshots = await _save_screenshots(images) if _real_images(images) else None
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
        screenshots=screenshots,
        update_screenshots=screenshots is not None,
        comment=_clean_comment(comment),
    )


@router.get("/groups/{group_id}/participation/me", response_model=GroupParticipationOut)
async def my_group_participation(
    group_id: int, user: CurrentUser, session: SessionDep
) -> GroupParticipationOut:
    """Where the current runner stands in this group, for the group page's
    "Я бегал(а)" button: no record yet, on the protocol without a result, or
    the result's moderation state."""
    group = await session.get(Group, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
    participation = await get_group_participation(session, user.id, group)
    if participation.other_group is not None:
        return GroupParticipationOut(
            status="other_group", other_group_name=participation.other_group.name
        )
    if participation.record is None:
        return GroupParticipationOut(status="none")
    if participation.result is None:
        return GroupParticipationOut(status="in_protocol", attendance_id=participation.record.id)
    return GroupParticipationOut(
        status=participation.result.status.value,
        attendance_id=participation.record.id,
    )


@router.get("/attendance/{attendance_id}/result", response_model=ResultOut)
async def get_result(attendance_id: int, session: SessionDep) -> Result:
    result = await session.scalar(
        select(Result).where(Result.attendance_record_id == attendance_id)
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No result for this record")
    return result
