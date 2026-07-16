from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus
from app.models.event import Event
from app.models.group import Group

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
    can render a "next up" teaser without a second request."""
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

    entries: list[AchievementEntry] = []
    for threshold in milestones:
        if len(rows) >= threshold:
            event_id, event_title, event_date = rows[threshold - 1]
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
