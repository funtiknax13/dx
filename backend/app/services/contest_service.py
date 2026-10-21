"""Contest phase derivation, entry submission/validation and voting.

Mirrors two patterns already established elsewhere rather than inventing new
ones: a contest's visible phase is a pure function of `now` vs its window
timestamps (see app.services.event_time for the same approach to
Event/Group), and entry moderation reuses ModerationStatus/the
reject-with-reason-then-resubmit flow already built for Result.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezone import now_msk
from app.models.contest import Contest, ContestEntry, ContestEntryValue, ContestField, ContestVote
from app.models.enums import ContestFieldType, ModerationStatus
from app.models.user import User


class ContestValidationError(ValueError):
    """field_id -> human-readable message, for every field that failed."""

    def __init__(self, errors: dict[int, str]) -> None:
        self.errors = errors
        super().__init__("Invalid contest entry values")


def _aware(dt: datetime) -> datetime:
    # SQLite (tests) drops tzinfo on round-trip — stored as UTC, same fix as
    # app.services.event_time._aware.
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def contest_phase(contest: Contest, now: datetime | None = None) -> str:
    """One of draft / upcoming / submissions_open / submissions_closed /
    voting_open / voting_closed. A window whose timestamp hasn't been set
    yet simply doesn't advance past that point — a contest the admin hasn't
    finished configuring reads as "not there yet" rather than erroring or
    guessing, and stays in its current phase indefinitely until the admin
    sets the next date."""
    now = now or now_msk()
    if not contest.is_published:
        return "draft"
    so = contest.submissions_open_at
    if so is None or now < _aware(so):
        return "upcoming"
    sc = contest.submissions_close_at
    if sc is None or now < _aware(sc):
        return "submissions_open"
    vo = contest.voting_open_at
    if vo is None or now < _aware(vo):
        return "submissions_closed"
    vc = contest.voting_close_at
    if vc is None or now < _aware(vc):
        return "voting_open"
    return "voting_closed"


# Human label for an admin-tools chip — the public API/frontend has its own
# (see frontend/src/pages/ContestsListPage.tsx's PHASE_LABEL), kept separate
# rather than shared since admin-tools is server-rendered Jinja, not JSON.
PHASE_LABELS_RU: dict[str, str] = {
    "draft": "Черновик",
    "upcoming": "Скоро начнётся",
    "submissions_open": "Приём заявок открыт",
    "submissions_closed": "Приём заявок завершён",
    "voting_open": "Идёт голосование",
    "voting_closed": "Итоги",
}


def can_submit(contest: Contest, now: datetime | None = None) -> bool:
    return contest_phase(contest, now) == "submissions_open"


def can_vote(contest: Contest, now: datetime | None = None) -> bool:
    return contest_phase(contest, now) == "voting_open"


def _validate_field_value(field: ContestField, raw: str) -> str | None:
    """None on success, else the error message for this field."""
    value = raw.strip()
    if not value:
        return "Обязательное поле" if field.required else None
    if field.field_type == ContestFieldType.number:
        try:
            float(value.replace(",", "."))
        except ValueError:
            return "Введите число"
    elif field.field_type == ContestFieldType.url:
        if not (value.startswith("http://") or value.startswith("https://")):
            return "Введите корректную ссылку (начинается с http:// или https://)"
    return None


async def get_entry(session: AsyncSession, contest_id: int, runner_id: int) -> ContestEntry | None:
    entry: ContestEntry | None = await session.scalar(
        select(ContestEntry).where(
            ContestEntry.contest_id == contest_id, ContestEntry.runner_id == runner_id
        )
    )
    return entry


async def submit_entry(
    session: AsyncSession,
    contest: Contest,
    runner: User,
    raw_values: dict[int, str],
    *,
    now: datetime | None = None,
) -> ContestEntry:
    """Create the runner's entry, or update + resubmit it for review if one
    already exists (and isn't already approved — settled, same as an
    approved Result). File-type fields (image/gpx) are passed here as
    already-saved media paths — the caller (the API route) handles the
    actual upload via media_service before calling this."""
    now = now or now_msk()
    if not can_submit(contest, now):
        raise ValueError("Приём конкурсных работ завершён, ожидайте результаты")

    fields = list(
        await session.scalars(
            select(ContestField)
            .where(ContestField.contest_id == contest.id)
            .order_by(ContestField.position)
        )
    )
    errors: dict[int, str] = {}
    for field in fields:
        error = _validate_field_value(field, raw_values.get(field.id, ""))
        if error:
            errors[field.id] = error
    if errors:
        raise ContestValidationError(errors)

    entry = await get_entry(session, contest.id, runner.id)
    if entry is not None and entry.status == ModerationStatus.approved:
        raise ValueError("Заявка уже подтверждена администратором, изменить её нельзя")

    if entry is None:
        entry = ContestEntry(
            contest_id=contest.id,
            runner_id=runner.id,
            status=ModerationStatus.pending,
            submitted_at=now,
        )
        session.add(entry)
    else:
        entry.status = ModerationStatus.pending
        entry.rejection_reason = None
        entry.submitted_at = now
    await session.flush()

    existing_values = {
        v.field_id: v
        for v in await session.scalars(
            select(ContestEntryValue).where(ContestEntryValue.entry_id == entry.id)
        )
    }
    for field in fields:
        value = raw_values.get(field.id, "").strip() or None
        if field.id in existing_values:
            existing_values[field.id].value = value
        else:
            session.add(ContestEntryValue(entry_id=entry.id, field_id=field.id, value=value))
    await session.flush()
    await session.refresh(entry, attribute_names=["values"])
    return entry


async def cast_vote(
    session: AsyncSession,
    contest: Contest,
    voter: User,
    entry: ContestEntry,
    *,
    now: datetime | None = None,
) -> ContestVote:
    """One vote per voter per contest — casting again just moves the same
    row to the new entry (see ContestVote). Rejects voting for your own
    entry, a sensible contest default even though it wasn't spelled out in
    the brief."""
    now = now or now_msk()
    if not can_vote(contest, now):
        raise ValueError("Голосование сейчас недоступно")
    if entry.contest_id != contest.id or entry.status != ModerationStatus.approved:
        raise ValueError("Эта заявка недоступна для голосования")
    if entry.runner_id == voter.id:
        raise ValueError("Нельзя голосовать за свою заявку")

    existing = await session.scalar(
        select(ContestVote).where(
            ContestVote.contest_id == contest.id, ContestVote.voter_id == voter.id
        )
    )
    if existing is not None:
        existing.entry_id = entry.id
        await session.flush()
        return existing

    vote = ContestVote(contest_id=contest.id, voter_id=voter.id, entry_id=entry.id)
    session.add(vote)
    await session.flush()
    return vote


async def vote_tally(session: AsyncSession, contest_id: int) -> dict[int, int]:
    rows = await session.execute(
        select(ContestVote.entry_id, func.count())
        .where(ContestVote.contest_id == contest_id)
        .group_by(ContestVote.entry_id)
    )
    return {entry_id: count for entry_id, count in rows.all()}


async def get_my_vote_entry_id(session: AsyncSession, contest_id: int, voter_id: int) -> int | None:
    entry_id: int | None = await session.scalar(
        select(ContestVote.entry_id).where(
            ContestVote.contest_id == contest_id, ContestVote.voter_id == voter_id
        )
    )
    return entry_id


async def set_placement(session: AsyncSession, entry: ContestEntry, placement: int | None) -> None:
    """Final ranking is always a human call (see Contest.results_published_at
    docstring) — this just records it, publish_results below is the separate
    step that makes it (and the vote tallies) visible to everyone."""
    entry.placement = placement
    await session.flush()


async def publish_results(
    session: AsyncSession, contest: Contest, *, now: datetime | None = None
) -> None:
    contest.results_published_at = now or now_msk()
    await session.flush()
