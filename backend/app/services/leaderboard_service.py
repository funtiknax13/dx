from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from sqlalchemy import func, select
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


async def compute_leaderboard(
    session: AsyncSession, metric: Metric, period: str = "all"
) -> list[LeaderboardEntry]:
    """Top runners by "dx" (count of finished attendances in groups that count
    toward the rating — i.e. "full DX") or "km" (sum of those groups'
    target_distance_km). Same counts_toward_rating filter as the community
    rating (excludes e.g. the short "P" group), just aggregated differently
    and windowed by calendar period instead of a rolling one."""
    agg = func.count(AttendanceRecord.id) if metric == "dx" else func.sum(Group.target_distance_km)
    stmt = (
        select(AttendanceRecord.runner_id, agg.label("value"))
        .join(Group, Group.id == AttendanceRecord.group_id)
        .where(
            AttendanceRecord.runner_id.is_not(None),
            AttendanceRecord.finish_status == FinishStatus.finished,
            Group.counts_toward_rating.is_(True),
        )
        .group_by(AttendanceRecord.runner_id)
    )
    window = _calendar_window(period)
    if window is not None:
        start, end = window
        stmt = stmt.join(Event, Event.id == Group.event_id).where(
            Event.date >= start, Event.date <= end
        )

    rows = (await session.execute(stmt)).all()
    value_map: dict[int, float] = {row.runner_id: float(row.value) for row in rows}

    if window is None:
        # Carry-over counts apply to the unwindowed total only — a runner with
        # a baseline but no tracked attendance yet should still show up.
        for runner_id, baseline in (await get_all_baselines(session)).items():
            addend = baseline.dx_count if metric == "dx" else baseline.total_km
            if addend:
                value_map[runner_id] = value_map.get(runner_id, 0.0) + addend

    if not value_map:
        return []

    users = await session.scalars(select(User).where(User.id.in_(value_map.keys())))
    entries = [
        LeaderboardEntry(
            runner_id=u.id,
            first_name=u.first_name,
            last_name=u.last_name,
            avatar=u.avatar,
            value=value_map[u.id],
        )
        for u in users
    ]
    entries.sort(key=lambda e: (-e.value, e.last_name, e.first_name))
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
