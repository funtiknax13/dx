import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import FinishStatus, ModerationStatus, ResultSource, UserRole
from app.models.group import Group
from app.models.result import Result
from tests.factories import make_attendance_with_result, make_event_group, make_user


@pytest.mark.asyncio
async def test_group_str_falls_back_when_event_date_was_never_queried(
    session: AsyncSession,
) -> None:
    """A Group just built and flushed in Python (the factory's return value,
    never itself the target of a SELECT) has no event_date yet — a
    column_property only gets its value from a query, unlike a plain mapped
    column. __str__ must degrade to the plain format rather than touch it
    (touching it here would trigger the exact implicit-IO crash this design
    exists to avoid — see the class docstring)."""
    org = await make_user(session, "org-groupstr0@example.com", UserRole.organizer)
    await session.commit()
    _, group = await make_event_group(session, org)
    await session.commit()

    assert str(group) == "X-10 @ City"


@pytest.mark.asyncio
async def test_group_str_includes_the_event_date_once_queried(session: AsyncSession) -> None:
    org = await make_user(session, "org-groupstr1@example.com", UserRole.organizer)
    await session.commit()
    _, group = await make_event_group(session, org)
    await session.commit()
    group_id = group.id

    result = await session.execute(select(Group).where(Group.id == group_id))
    queried_group = result.scalar_one()
    assert str(queried_group) == "X-10 @ City (01.05.2026)"


@pytest.mark.asyncio
async def test_group_str_works_on_a_bare_query_that_never_loaded_event(
    session: AsyncSession,
) -> None:
    """Regression guard: SQLAdmin populates relationship dropdowns (e.g.
    AttendanceRecord's "Group" field) via a plain `select(Group)` with no
    eager loading of the `event` relationship — calling str() on those rows
    must not touch that relationship (would raise MissingGreenlet on an
    async session) or this test would hang/crash instead of asserting."""
    org = await make_user(session, "org-groupstr2@example.com", UserRole.organizer)
    await session.commit()
    _, group = await make_event_group(session, org)
    await session.commit()
    group_id = group.id

    fresh_session_result = await session.execute(select(Group).where(Group.id == group_id))
    bare_group = fresh_session_result.scalar_one()
    assert str(bare_group) == "X-10 @ City (01.05.2026)"


def test_result_str_is_readable() -> None:
    result = Result(
        attendance_record_id=1,
        distance_km=10.0,
        duration_seconds=3000,
        pace_seconds_per_km=300.0,
        source=ResultSource.file,
        finish_status=FinishStatus.finished,
        status=ModerationStatus.approved,
    )
    assert str(result) == "10 км, 50:00 (финиш)"


def test_result_str_marks_dnf() -> None:
    result = Result(
        attendance_record_id=1,
        distance_km=5.0,
        duration_seconds=1230,
        pace_seconds_per_km=246.0,
        source=ResultSource.file,
        finish_status=FinishStatus.dnf,
        status=ModerationStatus.pending,
    )
    assert str(result) == "5 км, 20:30 (DNF)"


@pytest.mark.asyncio
async def test_result_str_works_on_a_bare_query_that_never_loaded_attendance_record(
    session: AsyncSession,
) -> None:
    """Same regression class as the Group test above — SQLAdmin shows this
    model's str() on AttendanceRecord's own edit form (the reverse "Result"
    field) from a query that never eager-loads attendance_record."""
    org = await make_user(session, "org-resultstr1@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-resultstr1@example.com")
    await session.commit()
    _, group = await make_event_group(session, org)
    record = await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.approved,
    )
    await session.commit()

    fresh = await session.execute(select(Result).where(Result.attendance_record_id == record.id))
    bare_result = fresh.scalar_one()
    assert str(bare_result) == "10 км, 50:00 (финиш)"
