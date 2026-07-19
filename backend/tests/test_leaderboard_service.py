from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, UserRole
from app.models.event import Event
from app.models.group import Group
from app.services.leaderboard_service import compute_leaderboard, compute_streak_leaderboard
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


@pytest.mark.asyncio
async def test_dx_leaderboard_excludes_groups_opted_out_of_rating(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-lb1@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-lb1@example.com")
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

    entries = await compute_leaderboard(session, "dx", "all")
    assert len(entries) == 1
    assert entries[0].runner_id == runner.id
    assert entries[0].value == 1.0


@pytest.mark.asyncio
async def test_km_leaderboard_sums_target_distance(session: AsyncSession) -> None:
    org = await make_user(session, "org-lb2@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-lb2@example.com")
    event, group1 = await make_event_group(session, org, target_km=25)
    event2 = Event(title="DX #2", date=date(2026, 5, 8), created_by=org.id)
    session.add(event2)
    await session.flush()
    group2 = Group(event_id=event2.id, location="City", name="X-33", target_distance_km=33)
    session.add(group2)
    await session.flush()

    await _finish(session, group1, runner.id)
    await _finish(session, group2, runner.id)
    await session.commit()

    entries = await compute_leaderboard(session, "km", "all")
    assert len(entries) == 1
    assert entries[0].value == 58.0


@pytest.mark.asyncio
async def test_leaderboard_orders_by_value_desc_then_name(session: AsyncSession) -> None:
    org = await make_user(session, "org-lb3@example.com", UserRole.organizer)
    r1 = await make_user(session, "r1-lb3@example.com")
    r2 = await make_user(session, "r2-lb3@example.com")
    _, group = await make_event_group(session, org, target_km=10)

    await _finish(session, group, r1.id)
    event2 = Event(title="DX #2", date=date(2026, 5, 8), created_by=org.id)
    session.add(event2)
    await session.flush()
    group2 = Group(event_id=event2.id, location="City", name="X-10", target_distance_km=10)
    session.add(group2)
    await session.flush()
    await _finish(session, group, r2.id)
    await _finish(session, group2, r2.id)
    await session.commit()

    entries = await compute_leaderboard(session, "dx", "all")
    assert [e.runner_id for e in entries] == [r2.id, r1.id]
    assert entries[0].value == 2.0
    assert entries[1].value == 1.0


@pytest.mark.asyncio
async def test_leaderboard_month_period_is_calendar_based(session: AsyncSession) -> None:
    org = await make_user(session, "org-lb4@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-lb4@example.com")
    now = datetime.now(UTC)
    this_month_start = now.date().replace(day=1)
    last_month_date = this_month_start - timedelta(days=1)

    this_month_event = Event(title="DX This Month", date=now.date(), created_by=org.id)
    last_month_event = Event(title="DX Last Month", date=last_month_date, created_by=org.id)
    session.add_all([this_month_event, last_month_event])
    await session.flush()
    g1 = Group(event_id=this_month_event.id, location="City", name="A", target_distance_km=10)
    g2 = Group(event_id=last_month_event.id, location="City", name="B", target_distance_km=10)
    session.add_all([g1, g2])
    await session.flush()

    await _finish(session, g1, runner.id)
    await _finish(session, g2, runner.id)
    await session.commit()

    entries = await compute_leaderboard(session, "dx", "month")
    assert len(entries) == 1
    assert entries[0].value == 1.0  # only this-month's event counts

    entries_all = await compute_leaderboard(session, "dx", "all")
    assert entries_all[0].value == 2.0


@pytest.mark.asyncio
async def test_leaderboard_empty_when_no_data(session: AsyncSession) -> None:
    entries = await compute_leaderboard(session, "dx", "all")
    assert entries == []


@pytest.mark.asyncio
async def test_streak_leaderboard_ranks_by_current_streak(session: AsyncSession) -> None:
    org = await make_user(session, "org-streak@example.com", UserRole.organizer)
    r1 = await make_user(session, "r1-streak@example.com")
    r2 = await make_user(session, "r2-streak@example.com")
    dates = [date(2026, 1, 4), date(2026, 1, 11), date(2026, 1, 18)]
    groups = []
    for i, d in enumerate(dates):
        event = Event(title=f"DX #{i}", date=d, created_by=org.id)
        session.add(event)
        await session.flush()
        group = Group(event_id=event.id, location="City", name=f"G{i}", target_distance_km=10)
        session.add(group)
        await session.flush()
        groups.append(group)

    # r1 attends all 3 -> current streak 3. r2 attends #0 and #2 (misses #1)
    # -> current streak 1 (only the trailing one counts).
    for g in groups:
        await _finish(session, g, r1.id)
    await _finish(session, groups[0], r2.id)
    await _finish(session, groups[2], r2.id)
    await session.commit()

    entries = await compute_streak_leaderboard(session)
    assert [e.runner_id for e in entries] == [r1.id, r2.id]
    assert entries[0].value == 3.0
    assert entries[1].value == 1.0


@pytest.mark.asyncio
async def test_streak_leaderboard_excludes_runners_with_zero_streak(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-streak0@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-streak0@example.com")
    e1 = Event(title="DX #1", date=date(2026, 1, 4), created_by=org.id)
    e2 = Event(title="DX #2", date=date(2026, 1, 11), created_by=org.id)
    session.add_all([e1, e2])
    await session.flush()
    g1 = Group(event_id=e1.id, location="City", name="G1", target_distance_km=10)
    g2 = Group(event_id=e2.id, location="City", name="G2", target_distance_km=10)
    session.add_all([g1, g2])
    await session.flush()

    # Someone else attends e2 so it counts as "imported" — otherwise a
    # zero-attendance event is treated as not-yet-run rather than missed.
    other = await make_user(session, "other-streak0@example.com")
    await _finish(session, g2, other.id)

    await _finish(session, g1, runner.id)  # only the older event -> streak 0 now
    await session.commit()

    entries = await compute_streak_leaderboard(session)
    assert [e.runner_id for e in entries] == [other.id]


@pytest.mark.asyncio
async def test_streak_ignores_a_not_yet_imported_event(session: AsyncSession) -> None:
    """A same-day event that hasn't had its CSV imported yet (zero
    AttendanceRecords for anyone) must not look like "everyone missed it" —
    it should simply not enter the sequence yet, leaving existing streaks
    intact until the roster is actually uploaded."""
    org = await make_user(session, "org-streak-noimport@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-streak-noimport@example.com")
    today = datetime.now(UTC).date()
    past_event = Event(title="DX Past", date=today - timedelta(days=7), created_by=org.id)
    today_event = Event(title="DX Today", date=today, created_by=org.id)
    session.add_all([past_event, today_event])
    await session.flush()
    past_group = Group(
        event_id=past_event.id, location="City", name="A", target_distance_km=10
    )
    today_group = Group(
        event_id=today_event.id, location="City", name="B", target_distance_km=10
    )
    session.add_all([past_group, today_group])
    await session.flush()

    await _finish(session, past_group, runner.id)
    # today_group deliberately has zero AttendanceRecords at all — nobody's
    # CSV has been imported for it yet.
    await session.commit()

    entries = await compute_streak_leaderboard(session)
    assert [e.runner_id for e in entries] == [runner.id]
    assert entries[0].value == 1.0


@pytest.mark.asyncio
async def test_streak_tie_cascades_to_finishes_this_month(session: AsyncSession) -> None:
    """Same current streak (1) for both -> r1 wins the tie via a higher
    finishes_month, exactly the same cascade the dx/km leaderboards use."""
    org = await make_user(session, "org-streak-tie1@example.com", UserRole.organizer)
    r1 = await make_user(session, "r1-streak-tie1@example.com")
    r2 = await make_user(session, "r2-streak-tie1@example.com")
    today = datetime.now(UTC).date()

    shared_event = Event(title="DX Shared", date=today, created_by=org.id)
    session.add(shared_event)
    await session.flush()
    shared_group = Group(
        event_id=shared_event.id, location="City", name="A", target_distance_km=10
    )
    session.add(shared_group)
    await session.flush()
    await _finish(session, shared_group, r1.id)
    await _finish(session, shared_group, r2.id)

    # A future event only r1 attends. _bulk_ranking_rows' month bucket has
    # no upper bound (unlike the streak's own date<=today event sequence),
    # so any date >= the start of this month still counts toward
    # finishes_month — even tomorrow — while never entering the streak
    # calculation itself. The tie stays exactly 1-1 on streak.
    tomorrow = today + timedelta(days=1)
    extra_event = Event(title="DX Extra", date=tomorrow, created_by=org.id)
    session.add(extra_event)
    await session.flush()
    extra_group = Group(
        event_id=extra_event.id, location="City", name="B", target_distance_km=10
    )
    session.add(extra_group)
    await session.flush()
    await _finish(session, extra_group, r1.id)
    await session.commit()

    entries = await compute_streak_leaderboard(session)
    assert [e.runner_id for e in entries] == [r1.id, r2.id]
    assert entries[0].value == entries[1].value == 1.0


@pytest.mark.asyncio
async def test_streak_tie_cascades_to_finishes_all_via_baseline(session: AsyncSession) -> None:
    """Tied on streak and every windowed metric -> a baseline's carry-over
    dx_count still settles it via finishes_all, even though baseline never
    contributes to the streak value itself."""
    org = await make_user(session, "org-streak-tie2@example.com", UserRole.organizer)
    r1 = await make_user(session, "r1-streak-tie2@example.com")
    r2 = await make_user(session, "r2-streak-tie2@example.com")
    today = datetime.now(UTC).date()

    shared_event = Event(title="DX Shared", date=today, created_by=org.id)
    session.add(shared_event)
    await session.flush()
    shared_group = Group(
        event_id=shared_event.id, location="City", name="A", target_distance_km=10
    )
    session.add(shared_group)
    await session.flush()
    await _finish(session, shared_group, r1.id)
    await _finish(session, shared_group, r2.id)
    await make_baseline(session, r1, dx_count=50)
    await session.commit()

    entries = await compute_streak_leaderboard(session)
    assert [e.runner_id for e in entries] == [r1.id, r2.id]
    assert entries[0].value == entries[1].value == 1.0


@pytest.mark.asyncio
async def test_baseline_adds_to_all_time_dx_and_km_but_not_month(session: AsyncSession) -> None:
    org = await make_user(session, "org-lb-base@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-lb-base@example.com")
    now = datetime.now(UTC)
    event = Event(title="DX Today", date=now.date(), created_by=org.id)
    session.add(event)
    await session.flush()
    group = Group(event_id=event.id, location="City", name="A", target_distance_km=10)
    session.add(group)
    await session.flush()
    await make_baseline(session, runner, dx_count=47, total_km=623.5)

    await _finish(session, group, runner.id)
    await session.commit()

    dx_all = await compute_leaderboard(session, "dx", "all")
    assert dx_all[0].value == 1 + 47
    km_all = await compute_leaderboard(session, "km", "all")
    assert km_all[0].value == 10 + 623.5

    dx_month = await compute_leaderboard(session, "dx", "month")
    assert dx_month[0].value == 1.0


@pytest.mark.asyncio
async def test_baseline_only_runner_still_appears_in_all_time_leaderboard(
    session: AsyncSession,
) -> None:
    runner = await make_user(session, "runner-lb-base2@example.com")
    await make_baseline(session, runner, dx_count=25, total_km=300.0)
    await session.commit()

    dx_all = await compute_leaderboard(session, "dx", "all")
    assert len(dx_all) == 1
    assert dx_all[0].runner_id == runner.id
    assert dx_all[0].value == 25.0

    assert await compute_leaderboard(session, "dx", "month") == []


@pytest.mark.asyncio
async def test_baseline_this_year_adds_to_year_leaderboard_when_year_matches(
    session: AsyncSession,
) -> None:
    runner = await make_user(session, "runner-lb-baseyear1@example.com")
    this_year = datetime.now(UTC).year
    await make_baseline(
        session,
        runner,
        dx_count=100,
        total_km=1000,
        dx_count_this_year=26,
        km_this_year=260,
        baseline_year=this_year,
    )
    await session.commit()

    dx_year = await compute_leaderboard(session, "dx", "year")
    assert len(dx_year) == 1
    assert dx_year[0].value == 26.0
    km_year = await compute_leaderboard(session, "km", "year")
    assert km_year[0].value == 260.0
    dx_all = await compute_leaderboard(session, "dx", "all")
    assert dx_all[0].value == 100.0


@pytest.mark.asyncio
async def test_baseline_this_year_ignored_when_year_does_not_match_leaderboard(
    session: AsyncSession,
) -> None:
    runner = await make_user(session, "runner-lb-baseyear2@example.com")
    last_year = datetime.now(UTC).year - 1
    await make_baseline(
        session,
        runner,
        dx_count=100,
        total_km=1000,
        dx_count_this_year=26,
        km_this_year=260,
        baseline_year=last_year,
    )
    await session.commit()

    assert await compute_leaderboard(session, "dx", "year") == []
    dx_all = await compute_leaderboard(session, "dx", "all")
    assert dx_all[0].value == 100.0


async def _event_group(session: AsyncSession, org, when, target_km: float, runner) -> None:
    event = Event(title=f"DX {when.isoformat()}", date=when, created_by=org.id)
    session.add(event)
    await session.flush()
    group = Group(event_id=event.id, location="City", name="A", target_distance_km=target_km)
    session.add(group)
    await session.flush()
    await _finish(session, group, runner.id)


@pytest.mark.asyncio
async def test_dx_leaderboard_month_tie_breaks_on_km(session: AsyncSession) -> None:
    org = await make_user(session, "org-tie-dx@example.com", UserRole.organizer)
    r1 = await make_user(session, "r1-tie-dx@example.com")
    r2 = await make_user(session, "r2-tie-dx@example.com")
    today = datetime.now(UTC).date()

    await _event_group(session, org, today, 30, r1)  # same finishes (1), r1 ran further
    await _event_group(session, org, today, 10, r2)
    await session.commit()

    entries = await compute_leaderboard(session, "dx", "month")
    assert [e.runner_id for e in entries] == [r1.id, r2.id]
    assert entries[0].value == entries[1].value == 1.0


@pytest.mark.asyncio
async def test_km_leaderboard_month_tie_breaks_on_finishes(session: AsyncSession) -> None:
    """km is the *primary* sort for this leaderboard — tied km should fall
    back to finish count, the mirror image of the dx leaderboard's cascade."""
    org = await make_user(session, "org-tie-km@example.com", UserRole.organizer)
    r1 = await make_user(session, "r1-tie-km@example.com")
    r2 = await make_user(session, "r2-tie-km@example.com")
    today = datetime.now(UTC).date()

    await _event_group(session, org, today, 20, r1)  # 20km in one run
    await _event_group(session, org, today, 10, r2)  # 20km across two runs
    await _event_group(session, org, today, 10, r2)
    await session.commit()

    entries = await compute_leaderboard(session, "km", "month")
    assert [e.runner_id for e in entries] == [r2.id, r1.id]
    assert entries[0].value == entries[1].value == 20.0


@pytest.mark.asyncio
async def test_km_leaderboard_month_tie_cascades_to_year_then_all(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-tie-km2@example.com", UserRole.organizer)
    r1 = await make_user(session, "r1-tie-km2@example.com")
    r2 = await make_user(session, "r2-tie-km2@example.com")
    today = datetime.now(UTC).date()
    this_month_start = today.replace(day=1)
    last_month_date = this_month_start - timedelta(days=1)

    # Tied this month (10km, 1 finish each) -> r1 has extra km earlier this
    # year (outside the calendar month window) to win on km_year.
    await _event_group(session, org, today, 10, r1)
    await _event_group(session, org, last_month_date, 15, r1)
    await _event_group(session, org, today, 10, r2)
    await session.commit()

    entries = await compute_leaderboard(session, "km", "month")
    assert [e.runner_id for e in entries] == [r1.id, r2.id]
