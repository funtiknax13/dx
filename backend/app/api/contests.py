import json
from typing import cast

from fastapi import APIRouter, HTTPException, Request, status
from fastapi import UploadFile as FastAPIUploadFile
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.datastructures import UploadFile

from app.api.deps import CurrentUser, OptionalUser, SessionDep
from app.core.config import settings
from app.models.contest import Contest, ContestEntry, ContestEntryValue, ContestField
from app.models.enums import ContestFieldType, ModerationStatus
from app.schemas.contest import (
    ContestDetail,
    ContestEntriesOut,
    ContestEntryValueOut,
    ContestFieldOut,
    ContestSummary,
    MyEntryOut,
    PublicEntryOut,
)
from app.schemas.group import RouteMap
from app.services import contest_service
from app.services.avatar_service import visible_avatar
from app.services.contest_service import ContestValidationError
from app.services.gpx_service import TrackParseError, parse_gpx
from app.services.media_service import (
    FileTooLargeError,
    InvalidFileTypeError,
    delete_media,
    media_path_to_fs,
    save_image,
    save_track_file,
)
from app.services.profile_completeness_service import stats_access_lock

router = APIRouter(prefix="/contests", tags=["contests"])

_FIELD_VISIBLE_PHASES = {
    "submissions_open",
    "submissions_closed",
    "voting_open",
    "voting_closed",
}
_ENTRIES_VISIBLE_PHASES = {"voting_open", "voting_closed"}


def _field_out(field: ContestField) -> ContestFieldOut:
    return ContestFieldOut(
        id=field.id,
        position=field.position,
        label=field.label,
        description=field.description,
        field_type=field.field_type.value,
        required=field.required,
        visible_to_voters=field.visible_to_voters,
        options=field.options,
    )


async def _get_published_contest(session: SessionDep, contest_id: int) -> Contest:
    contest = await session.get(Contest, contest_id)
    if contest is None or not contest.is_published:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contest not found")
    return contest


@router.get("", response_model=list[ContestSummary])
async def list_contests(session: SessionDep) -> list[ContestSummary]:
    contests = list(
        await session.scalars(
            select(Contest).where(Contest.is_published.is_(True)).order_by(Contest.id.desc())
        )
    )
    return [
        ContestSummary(
            id=c.id,
            title=c.title,
            cover_image=c.cover_image,
            phase=contest_service.contest_phase(c),
            submissions_open_at=c.submissions_open_at,
            submissions_close_at=c.submissions_close_at,
            voting_open_at=c.voting_open_at,
            voting_close_at=c.voting_close_at,
        )
        for c in contests
    ]


@router.get("/{contest_id}", response_model=ContestDetail)
async def contest_detail(contest_id: int, session: SessionDep) -> ContestDetail:
    contest = await _get_published_contest(session, contest_id)
    phase = contest_service.contest_phase(contest)
    fields = None
    if phase in _FIELD_VISIBLE_PHASES:
        rows = await session.scalars(
            select(ContestField)
            .where(ContestField.contest_id == contest_id)
            .order_by(ContestField.position)
        )
        fields = [_field_out(f) for f in rows]
    return ContestDetail(
        id=contest.id,
        title=contest.title,
        description=contest.description,
        cover_image=contest.cover_image,
        phase=phase,
        submissions_open_at=contest.submissions_open_at,
        submissions_close_at=contest.submissions_close_at,
        voting_open_at=contest.voting_open_at,
        voting_close_at=contest.voting_close_at,
        votes_visible_live=contest.votes_visible_live,
        results_published=contest.results_published_at is not None,
        max_entries_per_runner=contest.max_entries_per_runner,
        fields=fields,
    )


def _my_entry_out(entry: ContestEntry) -> MyEntryOut:
    return MyEntryOut(
        id=entry.id,
        status=entry.status.value,
        rejection_reason=entry.rejection_reason,
        submitted_at=entry.submitted_at,
        placement=entry.placement,
        values=[ContestEntryValueOut(field_id=v.field_id, value=v.value) for v in entry.values],
    )


@router.get("/{contest_id}/my-entries", response_model=list[MyEntryOut])
async def my_contest_entries(
    contest_id: int, user: CurrentUser, session: SessionDep
) -> list[MyEntryOut]:
    await _get_published_contest(session, contest_id)
    entries = await contest_service.get_entries(session, contest_id, user.id)
    for entry in entries:
        await session.refresh(entry, attribute_names=["values"])
    return [_my_entry_out(e) for e in entries]


@router.post(
    "/{contest_id}/entries", response_model=MyEntryOut, status_code=status.HTTP_201_CREATED
)
async def submit_contest_entry(
    contest_id: int, request: Request, user: CurrentUser, session: SessionDep
) -> MyEntryOut:
    contest = await _get_published_contest(session, contest_id)
    fields = list(
        await session.scalars(
            select(ContestField)
            .where(ContestField.contest_id == contest_id)
            .order_by(ContestField.position)
        )
    )

    form = await request.form()
    raw_entry_id = form.get("entry_id")
    entry_id = int(cast(str, raw_entry_id)) if raw_entry_id else None

    existing_values: dict[int, str | None] = {}
    if entry_id is not None:
        existing = await contest_service.get_owned_entry(session, contest_id, user.id, entry_id)
        if existing is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
        await session.refresh(existing, attribute_names=["values"])
        existing_values = {v.field_id: v.value for v in existing.values}

    raw_values: dict[int, str] = {}
    saved_paths: list[str] = []
    try:
        for field in fields:
            if field.field_type == ContestFieldType.image:
                uploads = [
                    cast(FastAPIUploadFile, part)
                    for part in form.getlist(f"field_{field.id}")
                    if isinstance(part, UploadFile) and part.filename
                ][: settings.contest_entry_max_images]
                if uploads:
                    paths = [await save_image(u, f"contests/{contest_id}") for u in uploads]
                    saved_paths.extend(paths)
                    raw_values[field.id] = json.dumps(paths)
                else:
                    # No new files this submit — keep whatever's already
                    # stored, so fixing a typo in another field doesn't
                    # force re-uploading photos every time.
                    raw_values[field.id] = existing_values.get(field.id) or ""
            elif field.field_type == ContestFieldType.gpx:
                part = form.get(f"field_{field.id}")
                if isinstance(part, UploadFile) and part.filename:
                    # request.form() hands back Starlette's base UploadFile,
                    # not fastapi's subclass — structurally identical for
                    # what save_image/save_track_file actually use.
                    upload = cast(FastAPIUploadFile, part)
                    path, _content, _ext = await save_track_file(upload, f"contests/{contest_id}")
                    saved_paths.append(path)
                    raw_values[field.id] = path
                else:
                    raw_values[field.id] = existing_values.get(field.id) or ""
            else:
                part = form.get(f"field_{field.id}")
                raw_values[field.id] = str(part) if part is not None else ""
    except (FileTooLargeError, InvalidFileTypeError) as exc:
        for path in saved_paths:
            delete_media(path)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    try:
        entry = await contest_service.submit_entry(
            session, contest, user, raw_values, entry_id=entry_id
        )
    except ContestValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"errors": {str(k): v for k, v in exc.errors.items()}},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return _my_entry_out(entry)


@router.get("/{contest_id}/entries", response_model=ContestEntriesOut)
async def list_contest_entries(
    contest_id: int, user: OptionalUser, session: SessionDep
) -> ContestEntriesOut:
    contest = await _get_published_contest(session, contest_id)
    phase = contest_service.contest_phase(contest)
    if phase not in _ENTRIES_VISIBLE_PHASES:
        return ContestEntriesOut(entries=[], votes_visible=False, my_vote_entry_id=None)

    visible_field_ids = {
        f.id
        for f in await session.scalars(
            select(ContestField).where(
                ContestField.contest_id == contest_id, ContestField.visible_to_voters.is_(True)
            )
        )
    }
    entries = list(
        await session.scalars(
            select(ContestEntry)
            .where(
                ContestEntry.contest_id == contest_id,
                ContestEntry.status == ModerationStatus.approved,
            )
            .options(selectinload(ContestEntry.values), selectinload(ContestEntry.runner))
            .order_by(ContestEntry.id)
        )
    )
    votes_visible = contest.votes_visible_live or contest.results_published_at is not None
    tally = await contest_service.vote_tally(session, contest_id) if votes_visible else {}

    my_vote_entry_id = (
        await contest_service.get_my_vote_entry_id(session, contest_id, user.id)
        if user is not None
        else None
    )

    out = [
        PublicEntryOut(
            id=e.id,
            runner_id=e.runner_id,
            runner_name=f"{e.runner.first_name} {e.runner.last_name}",
            avatar=visible_avatar(e.runner, user.id if user else None),
            placement=e.placement,
            vote_count=tally.get(e.id) if votes_visible else None,
            values=[
                ContestEntryValueOut(field_id=v.field_id, value=v.value)
                for v in e.values
                if v.field_id in visible_field_ids
            ],
        )
        for e in entries
    ]
    return ContestEntriesOut(
        entries=out, votes_visible=votes_visible, my_vote_entry_id=my_vote_entry_id
    )


@router.get("/{contest_id}/entries/{entry_id}/values/{field_id}/route-map", response_model=RouteMap)
async def entry_route_map(
    contest_id: int,
    entry_id: int,
    field_id: int,
    user: OptionalUser,
    session: SessionDep,
) -> RouteMap:
    """Same parse-and-return-points approach as GET /groups/{id}/route-map —
    lets a gpx-type entry field render as a map, not just a download link.
    Visible to the entry's own owner any time (so they can preview their
    submission before it's moderated), or to anyone once the entry is
    approved and the field is public — the same visibility list_contest_entries
    already applies to this field's raw value."""
    contest = await _get_published_contest(session, contest_id)
    entry = await session.get(ContestEntry, entry_id)
    field = await session.get(ContestField, field_id)
    if (
        entry is None
        or field is None
        or entry.contest_id != contest_id
        or field.contest_id != contest_id
        or field.field_type != ContestFieldType.gpx
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry field not found")

    is_owner = user is not None and user.id == entry.runner_id
    if not is_owner:
        phase = contest_service.contest_phase(contest)
        if (
            entry.status != ModerationStatus.approved
            or not field.visible_to_voters
            or phase not in _ENTRIES_VISIBLE_PHASES
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry field not found")

    value = await session.scalar(
        select(ContestEntryValue.value).where(
            ContestEntryValue.entry_id == entry_id, ContestEntryValue.field_id == field_id
        )
    )
    if not value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No route for this field")
    fs = media_path_to_fs(value)
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


@router.post("/{contest_id}/entries/{entry_id}/vote", status_code=status.HTTP_204_NO_CONTENT)
async def vote_for_entry(
    contest_id: int, entry_id: int, user: CurrentUser, session: SessionDep
) -> None:
    contest = await _get_published_contest(session, contest_id)
    reason, _missing = await stats_access_lock(session, user)
    if reason is not None:
        detail = (
            "Пройдите анкету новичка, чтобы голосовать."
            if reason == "survey_required"
            else "Заполните профиль до конца, чтобы голосовать."
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail)

    entry = await session.get(ContestEntry, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    try:
        await contest_service.cast_vote(session, contest, user, entry)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
