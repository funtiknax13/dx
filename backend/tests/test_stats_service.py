from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, UserRole
from app.models.event import Event
from app.models.group import Group
from app.services.stats_service import compute_profile_stats
from tests.factories import make_baseline, make_event_group, make_user


async def _finish(session: AsyncSession, group: Group, runner_id: int) -> None:
    session.add(
        AttendanceRecord(
            group_id=group.id,
            raw_name="Runner",
            runner_id=runner_id,
            finish_status=FinishStatus.finished,
        )
    )
    await session.flush()


async def _dnf(session: AsyncSession, group: Group, runner_id: int) -> None:
    session.add(
        AttendanceRecord(
            group_id=group.id,
            raw_name="Runner",
            runner_id=runner_id,
            finish_status=FinishStatus.dnf,
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_full_dx_excludes_groups_opted_out_of_rating(session: AsyncSession) -> None:
    org = await make_user(session, "org-stats1@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-stats1@example.com")
    _, full_group = await make_event_group(session, org, target_km=25)
    event2 = Event(title="DX #2", date=date(2026, 5, 8), created_by=org.id)
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

    await _finish(session, full_group, runner.id)
    await _finish(session, p_group, runner.id)
    await session.commit()

    stats = await compute_profile_stats(session, runner.id)
    assert stats.total_runs_count == 2
    assert stats.full_dx_count == 1
    assert stats.full_dx_km == 25.0


@pytest.mark.asyncio
async def test_first_run_date_is_earliest_finished_event(session: AsyncSession) -> None:
    org = await make_user(session, "org-stats2@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-stats2@example.com")
    early_event = Event(title="DX #1", date=date(2026, 3, 1), created_by=org.id)
    late_event = Event(title="DX #2", date=date(2026, 5, 1), created_by=org.id)
    session.add_all([early_event, late_event])
    await session.flush()
    early_group = Group(
        event_id=early_event.id, location="P", name="A", target_distance_km=10
    )
    late_group = Group(event_id=late_event.id, location="P", name="B", target_distance_km=10)
    session.add_all([early_group, late_group])
    await session.flush()

    await _finish(session, late_group, runner.id)
    await _finish(session, early_group, runner.id)
    await session.commit()

    stats = await compute_profile_stats(session, runner.id)
    assert stats.first_run_date == date(2026, 3, 1)


@pytest.mark.asyncio
async def test_streak_breaks_on_a_missed_past_event(session: AsyncSession) -> None:
    org = await make_user(session, "org-stats3@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-stats3@example.com")
    dates = [
        date(2026, 1, 4),
        date(2026, 1, 11),
        date(2026, 1, 18),
        date(2026, 1, 25),
        date(2026, 2, 1),
    ]
    groups = []
    for i, d in enumerate(dates):
        event = Event(title=f"DX #{i}", date=d, created_by=org.id)
        session.add(event)
        await session.flush()
        group = Group(event_id=event.id, location="P", name=f"G{i}", target_distance_km=10)
        session.add(group)
        await session.flush()
        groups.append(group)

    # Attend #0, #1, skip #2, attend #3, #4 -> longest=2, current=2.
    for i in (0, 1, 3, 4):
        await _finish(session, groups[i], runner.id)
    await session.commit()

    stats = await compute_profile_stats(session, runner.id)
    assert stats.longest_streak == 2
    assert stats.current_streak == 2


@pytest.mark.asyncio
async def test_streak_is_zero_when_most_recent_past_event_was_missed(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-stats4@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-stats4@example.com")
    e1 = Event(title="DX #1", date=date(2026, 1, 4), created_by=org.id)
    e2 = Event(title="DX #2", date=date(2026, 1, 11), created_by=org.id)
    session.add_all([e1, e2])
    await session.flush()
    g1 = Group(event_id=e1.id, location="P", name="G1", target_distance_km=10)
    g2 = Group(event_id=e2.id, location="P", name="G2", target_distance_km=10)
    session.add_all([g1, g2])
    await session.flush()

    await _finish(session, g1, runner.id)  # attended the older one only
    await session.commit()

    stats = await compute_profile_stats(session, runner.id)
    assert stats.longest_streak == 1
    assert stats.current_streak == 0


@pytest.mark.asyncio
async def test_total_runs_counts_dnf_attempts_too(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-stats5@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-stats5@example.com")
    _, group = await make_event_group(session, org, target_km=10)
    event2 = Event(title="DX #2", date=date(2026, 5, 8), created_by=org.id)
    session.add(event2)
    await session.flush()
    group2 = Group(event_id=event2.id, location="City", name="G2", target_distance_km=10)
    session.add(group2)
    await session.flush()

    await _finish(session, group, runner.id)
    await _dnf(session, group2, runner.id)
    await session.commit()

    stats = await compute_profile_stats(session, runner.id)
    assert stats.total_runs_count == 2


@pytest.mark.asyncio
async def test_baseline_adds_to_lifetime_totals_but_not_streak(session: AsyncSession) -> None:
    org = await make_user(session, "org-stats6@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-stats6@example.com")
    _, group = await make_event_group(session, org, target_km=10)
    await make_baseline(session, runner, dx_count=47, total_runs=50, total_km=623.5)

    await _finish(session, group, runner.id)
    await session.commit()

    stats = await compute_profile_stats(session, runner.id)
    assert stats.total_runs_count == 1 + 50
    assert stats.full_dx_count == 1 + 47
    assert stats.full_dx_km == 10 + 623.5
    # A carry-over count has no dated events behind it, so it can't
    # participate in a *consecutive* events streak.
    assert stats.current_streak == 1
    assert stats.longest_streak == 1


@pytest.mark.asyncio
async def test_no_baseline_is_a_no_op(session: AsyncSession) -> None:
    org = await make_user(session, "org-stats7@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-stats7@example.com")
    _, group = await make_event_group(session, org, target_km=10)

    await _finish(session, group, runner.id)
    await session.commit()

    stats = await compute_profile_stats(session, runner.id)
    assert stats.total_runs_count == 1
    assert stats.full_dx_count == 1
    assert stats.full_dx_km == 10
