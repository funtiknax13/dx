from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, Gender, ModerationStatus
from app.models.event import Event
from app.models.group import Group
from app.models.result import Result
from app.models.user import User
from app.services.baseline_service import get_all_baselines, get_baseline
from app.services.date_windows import calendar_window, current_year


def counts_toward_rating() -> ColumnElement[bool]:
    """A participation counts only when someone the community trusts vouched for
    it: an admin's CSV import (any non-self-reported `finished` record — a Result
    is optional there), or an admin-*approved* self-reported result. A runner's
    own self-reported run is just an unverified claim until then — a signup isn't
    a training, and neither is an unmoderated self-report. Callers must
    `outerjoin(Result, ...)` for the approval half of this condition to resolve."""
    return or_(
        AttendanceRecord.self_reported.is_(False),
        Result.status == ModerationStatus.approved,
    )


async def gender_filtered_ids(
    session: AsyncSession, ids: Iterable[int], gender: str
) -> set[int] | None:
    """Which of `ids` belong to runners of the requested gender, or None when no
    gender filter is asked for ("all"/anything but male/female). Runners who
    never set their gender (e.g. guest accounts) simply don't appear in the
    male/female rankings — only in the combined "all" view. Shared by the
    community rating and every leaderboard so they split identically."""
    if gender not in (Gender.male, Gender.female):
        return None
    matching = await session.scalars(
        select(User.id).where(User.id.in_(ids), User.gender == Gender(gender))
    )
    return set(matching)


@dataclass
class RatingEntry:
    runner_id: int
    first_name: str
    last_name: str
    avatar: str | None
    finished_count: int


def _count_query(period: str, runner_id: int | None = None) -> Select[tuple[int | None, int]]:
    """A CSV-imported participation counts as soon as the attendance is marked
    `finished` and linked to an account — uploading a Result is optional there.
    A *self-reported* run, by contrast, only counts once an admin approves its
    Result (see counts_toward_rating): the runner's own claim isn't proof of a
    training. Uploading a Result can flip finish_status to `dnf`, which drops it
    out of the count regardless. Groups with counts_toward_rating=False (e.g. a
    social/kids run) are excluded either way."""
    stmt = (
        select(
            AttendanceRecord.runner_id,
            func.count(AttendanceRecord.id).label("finished_count"),
        )
        .join(Group, Group.id == AttendanceRecord.group_id)
        .outerjoin(Result, Result.attendance_record_id == AttendanceRecord.id)
        .where(
            AttendanceRecord.runner_id.is_not(None),
            AttendanceRecord.finish_status == FinishStatus.finished,
            Group.counts_toward_rating.is_(True),
            counts_toward_rating(),
        )
        .group_by(AttendanceRecord.runner_id)
    )
    window = calendar_window(period)
    if window is not None:
        start, end = window
        stmt = stmt.join(Event, Event.id == Group.event_id)
        stmt = stmt.where(Event.date >= start, Event.date <= end)
    if runner_id is not None:
        stmt = stmt.where(AttendanceRecord.runner_id == runner_id)
    return stmt


@dataclass
class _RankingRow:
    """One runner's finishes/km at each of the three calendar windows this
    service cares about — used only to build the tie-break sort key below,
    never returned to callers directly."""

    finishes_month: int = 0
    km_month: float = 0.0
    finishes_year: int = 0
    km_year: float = 0.0
    finishes_all: int = 0
    km_all: float = 0.0


def _sort_key(row: _RankingRow, period: str) -> tuple[float, ...]:
    """Tie-break by narrowing-then-widening: same primary count -> compare km
    at the same window -> broaden to the next window and repeat. "all" has no
    broader window left, so it only gets the km fallback. Baseline carry-over
    (see RunnerBaseline) only ever contributes *_all figures unconditionally;
    it can also contribute to *_year if the admin tagged it with the current
    calendar year (see baseline_service) — it never reaches *_month, since a
    once-a-year-entered number can't be attributed to a specific month."""
    if period == "month":
        return (
            -row.finishes_month,
            -row.km_month,
            -row.finishes_year,
            -row.km_year,
            -row.finishes_all,
        )
    if period == "year":
        return (-row.finishes_year, -row.km_year, -row.finishes_all)
    return (-row.finishes_all, -row.km_all)


async def _bulk_ranking_rows(session: AsyncSession) -> dict[int, _RankingRow]:
    month_window = calendar_window("month")
    year_window = calendar_window("year")
    assert month_window is not None  # "month" always returns a window
    assert year_window is not None  # "year" always returns a window
    month_bound = month_window[0]
    year_bound = year_window[0]

    rows = await session.execute(
        select(
            AttendanceRecord.runner_id,
            func.sum(case((Event.date >= month_bound, 1), else_=0)).label("finishes_month"),
            func.coalesce(
                func.sum(case((Event.date >= month_bound, Group.target_distance_km), else_=0.0)),
                0.0,
            ).label("km_month"),
            func.sum(case((Event.date >= year_bound, 1), else_=0)).label("finishes_year"),
            func.coalesce(
                func.sum(case((Event.date >= year_bound, Group.target_distance_km), else_=0.0)),
                0.0,
            ).label("km_year"),
            func.count(AttendanceRecord.id).label("finishes_all"),
            func.coalesce(func.sum(Group.target_distance_km), 0.0).label("km_all"),
        )
        .select_from(AttendanceRecord)
        .join(Group, Group.id == AttendanceRecord.group_id)
        .join(Event, Event.id == Group.event_id)
        .outerjoin(Result, Result.attendance_record_id == AttendanceRecord.id)
        .where(
            AttendanceRecord.runner_id.is_not(None),
            AttendanceRecord.finish_status == FinishStatus.finished,
            Group.counts_toward_rating.is_(True),
            counts_toward_rating(),
        )
        .group_by(AttendanceRecord.runner_id)
    )

    result: dict[int, _RankingRow] = {
        r.runner_id: _RankingRow(
            finishes_month=int(r.finishes_month),
            km_month=float(r.km_month),
            finishes_year=int(r.finishes_year),
            km_year=float(r.km_year),
            finishes_all=int(r.finishes_all),
            km_all=float(r.km_all),
        )
        for r in rows
    }

    # Carry-over counts (see RunnerBaseline) — dx_count/total_km apply to the
    # unwindowed total unconditionally; dx_count_this_year/km_this_year only
    # when baseline_year is the current calendar year (otherwise they're
    # last year's — or some future year's admin never got around to yet —
    # and shouldn't count here). Either way, a runner with only baseline
    # data and no tracked attendance should still show up.
    this_year = current_year()
    for runner_id, baseline in (await get_all_baselines(session)).items():
        applies_this_year = baseline.baseline_year == this_year
        if not (
            baseline.dx_count
            or baseline.total_km
            or (applies_this_year and (baseline.dx_count_this_year or baseline.km_this_year))
        ):
            continue
        row = result.setdefault(runner_id, _RankingRow())
        row.finishes_all += baseline.dx_count
        row.km_all += baseline.total_km
        if applies_this_year:
            row.finishes_year += baseline.dx_count_this_year
            row.km_year += baseline.km_this_year

    return result


async def compute_rating(
    session: AsyncSession, period: str = "all", gender: str = "all"
) -> list[RatingEntry]:
    rows = await _bulk_ranking_rows(session)

    allowed = await gender_filtered_ids(session, rows.keys(), gender)
    if allowed is not None:
        rows = {rid: r for rid, r in rows.items() if rid in allowed}

    # A runner with no activity in the requested window shouldn't be ranked
    # in it at all — the bulk fetch above includes everyone with *any*
    # tracked/baseline activity, so filter down per period. "all" also
    # accepts a baseline-only km figure (dx_count could be 0 while total_km
    # isn't, or vice versa).
    if period == "month":
        rows = {rid: r for rid, r in rows.items() if r.finishes_month > 0}
    elif period == "year":
        rows = {rid: r for rid, r in rows.items() if r.finishes_year > 0}
    else:
        rows = {rid: r for rid, r in rows.items() if r.finishes_all > 0 or r.km_all > 0}

    if not rows:
        return []

    finished_count_attr = {
        "month": "finishes_month",
        "year": "finishes_year",
        "all": "finishes_all",
    }[period]

    users = await session.scalars(select(User).where(User.id.in_(rows.keys())))
    entries = [
        RatingEntry(
            runner_id=u.id,
            first_name=u.first_name,
            last_name=u.last_name,
            avatar=u.avatar,
            finished_count=getattr(rows[u.id], finished_count_attr),
        )
        for u in users
    ]
    entries.sort(key=lambda e: (*_sort_key(rows[e.runner_id], period), e.last_name, e.first_name))
    return entries


async def runner_finished_count(
    session: AsyncSession, runner_id: int, period: str = "all"
) -> int:
    row = (await session.execute(_count_query(period, runner_id=runner_id))).first()
    count = int(row.finished_count) if row else 0
    if period == "all":
        baseline = await get_baseline(session, runner_id)
        if baseline:
            count += baseline.dx_count
    return count
