from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus
from app.models.event import Event
from app.models.group import Group
from app.models.user import User
from app.services.baseline_service import get_all_baselines, get_baseline


@dataclass
class RatingEntry:
    runner_id: int
    first_name: str
    last_name: str
    avatar: str | None
    finished_count: int


def _period_window(period: str) -> tuple[datetime, datetime] | None:
    """(start, now) for "year"/"month" — a real window, not just a lower bound, so
    a group scheduled months from now doesn't count towards "this month" just
    because its date happens to be >= today - 30 days."""
    now = datetime.now(UTC)
    if period == "year":
        return now - timedelta(days=365), now
    if period == "month":
        return now - timedelta(days=30), now
    return None  # "all"


def _count_query(period: str, runner_id: int | None = None) -> Select[tuple[int | None, int]]:
    """A participation counts for rating as soon as the attendance is marked
    `finished` and linked to an account — uploading a Result is optional (see
    CLAUDE.md): CSV import already marks everyone `finished` by default, and that
    alone is enough to count. Uploading a Result can later flip it to `dnf`, which
    drops it out of the count; a *pending* (not yet approved) Result doesn't change
    finish_status, so it keeps counting either way. Groups with
    counts_toward_rating=False (e.g. a social/kids run) are excluded regardless."""
    stmt = (
        select(
            AttendanceRecord.runner_id,
            func.count(AttendanceRecord.id).label("finished_count"),
        )
        .join(Group, Group.id == AttendanceRecord.group_id)
        .where(
            AttendanceRecord.runner_id.is_not(None),
            AttendanceRecord.finish_status == FinishStatus.finished,
            Group.counts_toward_rating.is_(True),
        )
        .group_by(AttendanceRecord.runner_id)
    )
    window = _period_window(period)
    if window is not None:
        start, end = window
        stmt = stmt.join(Event, Event.id == Group.event_id)
        stmt = stmt.where(Event.date >= start.date(), Event.date <= end.date())
    if runner_id is not None:
        stmt = stmt.where(AttendanceRecord.runner_id == runner_id)
    return stmt


@dataclass
class _RankingRow:
    """One runner's finishes/km at each of the three rolling windows this
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
    (see RunnerBaseline) only ever contributes to the *_all figures — it has
    no dated events, so it can't participate in a month/year window."""
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
    month_window = _period_window("month")
    year_window = _period_window("year")
    assert month_window is not None  # "month" always returns a window
    assert year_window is not None  # "year" always returns a window
    month_bound = month_window[0].date()
    year_bound = year_window[0].date()

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
        .where(
            AttendanceRecord.runner_id.is_not(None),
            AttendanceRecord.finish_status == FinishStatus.finished,
            Group.counts_toward_rating.is_(True),
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

    # Carry-over counts (see RunnerBaseline) apply to the unwindowed total
    # only — a runner with a baseline but no tracked attendance yet should
    # still show up.
    for runner_id, baseline in (await get_all_baselines(session)).items():
        if not (baseline.dx_count or baseline.total_km):
            continue
        row = result.setdefault(runner_id, _RankingRow())
        row.finishes_all += baseline.dx_count
        row.km_all += baseline.total_km

    return result


async def compute_rating(session: AsyncSession, period: str = "all") -> list[RatingEntry]:
    rows = await _bulk_ranking_rows(session)

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
