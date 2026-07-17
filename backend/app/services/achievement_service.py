from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus
from app.models.event import Event
from app.models.group import Group
from app.services.baseline_service import get_baseline, get_baselines

# Full-DX-count thresholds shown as milestone badges.
ACHIEVEMENT_MILESTONES: list[int] = [25, 50, 100, 150, 200, 250, 300]


@dataclass
class AchievementEntry:
    threshold: int
    reached: bool
    reached_at: date | None
    event_id: int | None
    event_title: str | None


async def compute_achievements(
    session: AsyncSession, runner_id: int, milestones: list[int] | None = None
) -> list[AchievementEntry]:
    """One entry per configured milestone, in ascending order. A reached
    milestone carries the date/event of the exact "full DX" attendance that
    crossed it — the Nth one chronologically by event date, out of the same
    "finished + counts_toward_rating" set used for rating/streak/km. Includes
    unreached milestones too (reached=False, no date/event) so the frontend
    can render a "next up" teaser without a second request.

    An admin-entered RunnerBaseline (carry-over count from before this
    platform existed) counts as if it happened first — a threshold covered
    entirely by it is reached with no date/event (there's no real run to
    attribute it to); a threshold it merely gets a runner *close* to still
    resolves to the actual tracked run that crossed it."""
    milestones = ACHIEVEMENT_MILESTONES if milestones is None else milestones
    rows = (
        await session.execute(
            select(Event.id, Event.title, Event.date)
            .select_from(AttendanceRecord)
            .join(Group, Group.id == AttendanceRecord.group_id)
            .join(Event, Event.id == Group.event_id)
            .where(
                AttendanceRecord.runner_id == runner_id,
                AttendanceRecord.finish_status == FinishStatus.finished,
                Group.counts_toward_rating.is_(True),
            )
            .order_by(Event.date)
        )
    ).all()

    baseline = await get_baseline(session, runner_id)
    baseline_dx = baseline.dx_count if baseline else 0
    total = baseline_dx + len(rows)

    entries: list[AchievementEntry] = []
    for threshold in milestones:
        if threshold <= baseline_dx:
            entries.append(
                AchievementEntry(
                    threshold=threshold,
                    reached=True,
                    reached_at=None,
                    event_id=None,
                    event_title=None,
                )
            )
        elif total >= threshold:
            event_id, event_title, event_date = rows[threshold - baseline_dx - 1]
            entries.append(
                AchievementEntry(
                    threshold=threshold,
                    reached=True,
                    reached_at=event_date,
                    event_id=event_id,
                    event_title=event_title,
                )
            )
        else:
            entries.append(
                AchievementEntry(
                    threshold=threshold,
                    reached=False,
                    reached_at=None,
                    event_id=None,
                    event_title=None,
                )
            )
    return entries


async def get_latest_thresholds(
    session: AsyncSession, runner_ids: list[int], milestones: list[int] | None = None
) -> dict[int, int]:
    """Highest milestone each runner has reached, for many runners at once —
    e.g. to badge a whole protocol table without one compute_achievements
    call (and its own query) per row. Runners with no reached milestone are
    simply absent from the result. Includes each runner's RunnerBaseline
    carry-over count, same as compute_achievements."""
    if not runner_ids:
        return {}
    milestones = ACHIEVEMENT_MILESTONES if milestones is None else milestones
    rows = await session.execute(
        select(AttendanceRecord.runner_id, func.count(AttendanceRecord.id))
        .join(Group, Group.id == AttendanceRecord.group_id)
        .where(
            AttendanceRecord.runner_id.in_(runner_ids),
            AttendanceRecord.finish_status == FinishStatus.finished,
            Group.counts_toward_rating.is_(True),
        )
        .group_by(AttendanceRecord.runner_id)
    )
    counts: dict[int, int] = {runner_id: count for runner_id, count in rows}
    baselines = await get_baselines(session, runner_ids)

    result: dict[int, int] = {}
    for runner_id in set(counts) | set(baselines):
        total = counts.get(runner_id, 0) + (
            baselines[runner_id].dx_count if runner_id in baselines else 0
        )
        reached = [m for m in milestones if total >= m]
        if reached:
            result[runner_id] = max(reached)
    return result
