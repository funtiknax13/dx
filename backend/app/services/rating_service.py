from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus
from app.models.event import Event
from app.models.group import Group
from app.models.user import User


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


async def compute_rating(session: AsyncSession, period: str = "all") -> list[RatingEntry]:
    counts = (await session.execute(_count_query(period))).all()
    count_map = {row.runner_id: row.finished_count for row in counts}
    if not count_map:
        return []

    users = await session.scalars(select(User).where(User.id.in_(count_map.keys())))
    entries = [
        RatingEntry(
            runner_id=u.id,
            first_name=u.first_name,
            last_name=u.last_name,
            avatar=u.avatar,
            finished_count=count_map[u.id],
        )
        for u in users
    ]
    entries.sort(key=lambda e: (-e.finished_count, e.last_name, e.first_name))
    return entries


async def runner_finished_count(
    session: AsyncSession, runner_id: int, period: str = "all"
) -> int:
    row = (await session.execute(_count_query(period, runner_id=runner_id))).first()
    return int(row.finished_count) if row else 0
