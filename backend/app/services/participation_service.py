"""A runner's standing in one group's distance family: do they have a record
there, does it have a result, and where is that result in moderation."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import ModerationStatus
from app.models.group import Group
from app.models.result import Result
from app.services.group_service import family_group_ids


@dataclass
class GroupParticipation:
    record: AttendanceRecord | None
    result: Result | None
    # Set when the runner has an unresolved (pending or approved) record in a
    # *different* group of the same event — a runner is in one group per
    # event, so that's a conflict to surface, not a gap to fill. A *rejected*
    # record elsewhere doesn't count: it was already turned down as wrong, so
    # it's exactly the "moved to the right group" case, not a duplicate.
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

    elsewhere = await session.scalar(
        select(AttendanceRecord)
        .join(Group, Group.id == AttendanceRecord.group_id)
        .where(
            Group.event_id == group.event_id,
            AttendanceRecord.runner_id == runner_id,
            AttendanceRecord.group_id.not_in(family_ids),
        )
        .order_by(AttendanceRecord.id)
        .limit(1)
    )
    if elsewhere is None:
        return GroupParticipation(record=None, result=None, other_group=None)

    other_result = await session.scalar(
        select(Result).where(Result.attendance_record_id == elsewhere.id)
    )
    if other_result is not None and other_result.status == ModerationStatus.rejected:
        # Turned down in the wrong group — reusable: submitting here moves it,
        # same as a record with no result yet in this group's own family.
        return GroupParticipation(record=elsewhere, result=other_result, other_group=None)

    other_group = await session.get(Group, elsewhere.group_id)
    return GroupParticipation(record=None, result=None, other_group=other_group)
