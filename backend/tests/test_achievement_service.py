from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, UserRole
from app.models.event import Event
from app.models.group import Group
from app.services.achievement_service import compute_achievements, get_latest_thresholds
from tests.factories import make_event_group, make_user


async def _dx_event(session: AsyncSession, org, when: date, runner_id: int) -> None:
    event = Event(title=f"DX #{when.isoformat()}", date=when, created_by=org.id)
    session.add(event)
    await session.flush()
    group = Group(event_id=event.id, location="City", name="X-10", target_distance_km=10)
    session.add(group)
    await session.flush()
    session.add(
        AttendanceRecord(
            group_id=group.id,
            raw_name="Runner",
            runner_id=runner_id,
            finish_status=FinishStatus.finished,
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_reached_milestone_points_at_the_nth_chronological_dx(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-ach1@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-ach1@example.com")
    dates = [date(2026, 1, 4), date(2026, 1, 11), date(2026, 1, 18)]
    for d in dates:
        await _dx_event(session, org, d, runner.id)
    await session.commit()

    entries = await compute_achievements(session, runner.id, milestones=[2, 5])
    by_threshold = {e.threshold: e for e in entries}

    assert by_threshold[2].reached is True
    assert by_threshold[2].reached_at == date(2026, 1, 11)  # 2nd chronologically
    assert by_threshold[2].event_title == "DX #2026-01-11"

    assert by_threshold[5].reached is False
    assert by_threshold[5].reached_at is None
    assert by_threshold[5].event_id is None


@pytest.mark.asyncio
async def test_achievements_excludes_groups_opted_out_of_rating(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-ach2@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-ach2@example.com")
    _, full_group = await make_event_group(session, org, target_km=10)
    event2 = Event(title="P event", date=date(2026, 2, 1), created_by=org.id)
    session.add(event2)
    await session.flush()
    p_group = Group(
        event_id=event2.id,
        location="P",
        name="P-10",
        target_distance_km=10,
        counts_toward_rating=False,
    )
    session.add(p_group)
    await session.flush()

    session.add(
        AttendanceRecord(
            group_id=full_group.id,
            raw_name="Runner",
            runner_id=runner.id,
            finish_status=FinishStatus.finished,
        )
    )
    session.add(
        AttendanceRecord(
            group_id=p_group.id,
            raw_name="Runner",
            runner_id=runner.id,
            finish_status=FinishStatus.finished,
        )
    )
    await session.commit()

    entries = await compute_achievements(session, runner.id, milestones=[1, 2])
    by_threshold = {e.threshold: e for e in entries}
    assert by_threshold[1].reached is True
    assert by_threshold[2].reached is False  # the P-group run doesn't count


@pytest.mark.asyncio
async def test_achievements_returns_all_milestones_unreached_with_no_history(
    session: AsyncSession,
) -> None:
    runner = await make_user(session, "runner-ach3@example.com")
    await session.commit()

    entries = await compute_achievements(session, runner.id, milestones=[25, 50])
    assert [e.reached for e in entries] == [False, False]


@pytest.mark.asyncio
async def test_get_latest_thresholds_picks_the_highest_reached_per_runner(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-ach4@example.com", UserRole.organizer)
    r1 = await make_user(session, "runner-ach4a@example.com")
    r2 = await make_user(session, "runner-ach4b@example.com")
    r3 = await make_user(session, "runner-ach4c@example.com")

    for d in [date(2026, 1, 4), date(2026, 1, 11), date(2026, 1, 18)]:
        await _dx_event(session, org, d, r1.id)  # r1: 3 full DX
    await _dx_event(session, org, date(2026, 2, 1), r2.id)  # r2: 1 full DX
    # r3 has no attendance at all.
    await session.commit()

    result = await get_latest_thresholds(session, [r1.id, r2.id, r3.id], milestones=[1, 2, 3])
    assert result == {r1.id: 3, r2.id: 1}
    assert r3.id not in result
