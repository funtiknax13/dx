from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus
from app.models.event import Event
from app.models.group import Group


@dataclass
class ProfileStats:
    first_run_date: date | None
    total_runs_count: int
    full_dx_count: int
    full_dx_km: float
    current_streak: int
    longest_streak: int


async def compute_profile_stats(session: AsyncSession, runner_id: int) -> ProfileStats:
    """Lifetime participation stats for a runner's profile. "Full DX" means a
    finished attendance in a group with counts_toward_rating=True — the same
    flag already used to keep social/kids groups (e.g. the short "P" group)
    out of the community rating, reused here for the same "does this count as
    a real DX" distinction. "Total runs" counts every finished attendance,
    including those excluded groups."""
    total_runs = await session.scalar(
        select(func.count(AttendanceRecord.id)).where(
            AttendanceRecord.runner_id == runner_id,
            AttendanceRecord.finish_status == FinishStatus.finished,
        )
    )

    full_dx_row = (
        await session.execute(
            select(
                func.count(AttendanceRecord.id),
                func.coalesce(func.sum(Group.target_distance_km), 0.0),
            )
            .join(Group, Group.id == AttendanceRecord.group_id)
            .where(
                AttendanceRecord.runner_id == runner_id,
                AttendanceRecord.finish_status == FinishStatus.finished,
                Group.counts_toward_rating.is_(True),
            )
        )
    ).first()
    full_dx_count = int(full_dx_row[0]) if full_dx_row else 0
    full_dx_km = float(full_dx_row[1]) if full_dx_row else 0.0

    first_run_date = await session.scalar(
        select(func.min(Event.date))
        .join(Group, Group.event_id == Event.id)
        .join(AttendanceRecord, AttendanceRecord.group_id == Group.id)
        .where(
            AttendanceRecord.runner_id == runner_id,
            AttendanceRecord.finish_status == FinishStatus.finished,
        )
    )

    current_streak, longest_streak = await _compute_streak(session, runner_id)

    return ProfileStats(
        first_run_date=first_run_date,
        total_runs_count=total_runs or 0,
        full_dx_count=full_dx_count,
        full_dx_km=full_dx_km,
        current_streak=current_streak,
        longest_streak=longest_streak,
    )


async def _compute_streak(session: AsyncSession, runner_id: int) -> tuple[int, int]:
    """Longest and current run of *consecutive* past events attended (any
    group, including "P" — showing up at all keeps the streak alive, "full
    DX" is a separate, stricter stat). Consecutive is relative to events
    actually held, not calendar weeks, so a week with no event scheduled
    doesn't break anyone's streak."""
    today = datetime.now(UTC).date()
    event_ids = (
        await session.scalars(select(Event.id).where(Event.date <= today).order_by(Event.date))
    ).all()
    if not event_ids:
        return 0, 0

    attended_ids = set(
        await session.scalars(
            select(Group.event_id)
            .join(AttendanceRecord, AttendanceRecord.group_id == Group.id)
            .where(
                AttendanceRecord.runner_id == runner_id,
                AttendanceRecord.finish_status == FinishStatus.finished,
            )
            .distinct()
        )
    )

    longest = current = 0
    for event_id in event_ids:
        if event_id in attended_ids:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    # `current` after the loop is the run trailing the most recent past
    # event — exactly the "current streak" (0 if that event was missed).
    return current, longest
