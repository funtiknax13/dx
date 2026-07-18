from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus
from app.models.event import Event
from app.models.group import Group
from app.models.user import User
from app.services.baseline_service import get_all_baselines

Metric = Literal["dx", "km"]


@dataclass
class LeaderboardEntry:
    runner_id: int
    first_name: str
    last_name: str
    avatar: str | None
    value: float


def _calendar_window(period: str) -> tuple[date, date] | None:
    """(start, today) for "year"/"month" — a *calendar* window (Jan 1 / the
    1st of this month, through today), unlike rating_service's rolling
    30/365-day windows. These are plain informational leaderboards, not the
    community rating (still being redesigned separately), so "this month"
    means the actual current calendar month, not a trailing 30 days."""
    today = datetime.now(UTC).date()
    if period == "year":
        return date(today.year, 1, 1), today
    if period == "month":
        return date(today.year, today.month, 1), today
    return None


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


def _sort_key(row: _RankingRow, metric: Metric, period: str) -> tuple[float, ...]:
    """Tie-break by narrowing-then-widening: same primary value -> compare
    the other metric at the same window -> broaden to the next window and
    repeat. Which metric is primary depends on which leaderboard this is —
    "dx" ranks by finishes first, "km" ranks by km first — but both fall
    back to the other metric, then broader windows, the same way. Baseline
    carry-over (see RunnerBaseline) only ever contributes to the *_all
    figures — it has no dated events, so it can't participate in a
    month/year window."""
    if metric == "dx":
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
    if period == "month":
        return (
            -row.km_month,
            -row.finishes_month,
            -row.km_year,
            -row.finishes_year,
            -row.km_all,
        )
    if period == "year":
        return (-row.km_year, -row.finishes_year, -row.km_all)
    return (-row.km_all, -row.finishes_all)


async def _bulk_ranking_rows(session: AsyncSession) -> dict[int, _RankingRow]:
    month_window = _calendar_window("month")
    year_window = _calendar_window("year")
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


async def compute_leaderboard(
    session: AsyncSession, metric: Metric, period: str = "all"
) -> list[LeaderboardEntry]:
    """Top runners by "dx" (count of finished attendances in groups that count
    toward the rating — i.e. "full DX") or "km" (sum of those groups'
    target_distance_km). Same counts_toward_rating filter as the community
    rating (excludes e.g. the short "P" group), just aggregated differently
    and windowed by calendar period instead of a rolling one. Ties are broken
    by cascading through the other metric and broader windows — see
    _sort_key."""
    rows = await _bulk_ranking_rows(session)

    # A runner with no activity in the requested window shouldn't be ranked
    # in it at all — the bulk fetch above includes everyone with *any*
    # tracked/baseline activity, so filter down per period. "all" also
    # accepts a baseline-only figure in just one of dx_count/total_km.
    if period == "month":
        rows = {rid: r for rid, r in rows.items() if r.finishes_month > 0}
    elif period == "year":
        rows = {rid: r for rid, r in rows.items() if r.finishes_year > 0}
    else:
        rows = {rid: r for rid, r in rows.items() if r.finishes_all > 0 or r.km_all > 0}

    if not rows:
        return []

    value_attr = {
        "dx": {"month": "finishes_month", "year": "finishes_year", "all": "finishes_all"},
        "km": {"month": "km_month", "year": "km_year", "all": "km_all"},
    }[metric][period]

    users = await session.scalars(select(User).where(User.id.in_(rows.keys())))
    entries = [
        LeaderboardEntry(
            runner_id=u.id,
            first_name=u.first_name,
            last_name=u.last_name,
            avatar=u.avatar,
            value=float(getattr(rows[u.id], value_attr)),
        )
        for u in users
    ]
    entries.sort(
        key=lambda e: (*_sort_key(rows[e.runner_id], metric, period), e.last_name, e.first_name)
    )
    return entries


async def compute_streak_leaderboard(session: AsyncSession) -> list[LeaderboardEntry]:
    """Top runners by *current* streak of consecutive attended past events —
    any group counts, including "P" (see app.services.stats_service for the
    per-profile version of this same algorithm). Period-agnostic: a streak is
    inherently "as of right now", there's no "this year"/"this month" streak.
    Only runners with a live streak (> 0) are included."""
    today = datetime.now(UTC).date()
    event_ids = list(
        await session.scalars(select(Event.id).where(Event.date <= today).order_by(Event.date))
    )
    if not event_ids:
        return []

    rows = await session.execute(
        select(AttendanceRecord.runner_id, Group.event_id)
        .join(Group, Group.id == AttendanceRecord.group_id)
        .where(
            AttendanceRecord.runner_id.is_not(None),
            AttendanceRecord.finish_status == FinishStatus.finished,
        )
        .distinct()
    )
    attended_by_runner: dict[int, set[int]] = defaultdict(set)
    for runner_id, event_id in rows:
        attended_by_runner[runner_id].add(event_id)

    streak_map: dict[int, int] = {}
    for runner_id, attended in attended_by_runner.items():
        current = 0
        for event_id in event_ids:
            current = current + 1 if event_id in attended else 0
        if current > 0:
            streak_map[runner_id] = current

    if not streak_map:
        return []

    users = await session.scalars(select(User).where(User.id.in_(streak_map.keys())))
    entries = [
        LeaderboardEntry(
            runner_id=u.id,
            first_name=u.first_name,
            last_name=u.last_name,
            avatar=u.avatar,
            value=float(streak_map[u.id]),
        )
        for u in users
    ]
    entries.sort(key=lambda e: (-e.value, e.last_name, e.first_name))
    return entries
