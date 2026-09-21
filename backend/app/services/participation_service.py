"""A runner's standing in one group's distance family: do they have a record
there, does it have a result, and where is that result in moderation."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.group import Group
from app.models.result import Result
from app.services.group_service import family_group_ids


@dataclass
class GroupParticipation:
    record: AttendanceRecord | None
    result: Result | None
    # Set when the runner has no record in this group's distance family but
    # does have one in a *different* group of the same event — a runner is in
    # one group per event, so that's a conflict to surface, not a gap to fill.
    other_group: Group | None


async def get_group_participation(
    session: AsyncSession, runner_id: int, group: Group
) -> GroupParticipation:
    family_ids = await family_group_ids(session, group)
    record = await session.scalar(
        select(AttendanceRecord)
        .where(
            AttendanceRecord.group_id.in_(family_ids),
            AttendanceRecord.runner_id == runner_id,
        )
        .order_by(AttendanceRecord.id)
        .limit(1)
    )
    if record is not None:
        result = await session.scalar(
            select(Result).where(Result.attendance_record_id == record.id)
        )
        return GroupParticipation(record=record, result=result, other_group=None)

    other_group = await session.scalar(
        select(Group)
        .join(AttendanceRecord, AttendanceRecord.group_id == Group.id)
        .where(
            Group.event_id == group.event_id,
            AttendanceRecord.runner_id == runner_id,
            AttendanceRecord.group_id.not_in(family_ids),
        )
        .order_by(AttendanceRecord.id)
        .limit(1)
    )
    return GroupParticipation(record=None, result=None, other_group=other_group)
