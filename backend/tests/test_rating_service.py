from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, ModerationStatus, UserRole
from app.models.event import Event
from app.models.group import Group
from app.services.rating_service import compute_rating, runner_finished_count
from tests.factories import (
    make_attendance_with_result,
    make_baseline,
    make_event_group,
    make_user,
)


async def _bare_attendance(
    session: AsyncSession, group, runner, *, finish_status: FinishStatus
) -> AttendanceRecord:
    """An AttendanceRecord with no Result at all — e.g. straight off a CSV import,
    before the (optional) result upload."""
    rec = AttendanceRecord(
        group_id=group.id,
        raw_name=f"{runner.first_name} {runner.last_name}",
        runner_id=runner.id,
        finish_status=finish_status,
    )
    session.add(rec)
    await session.flush()
    return rec


@pytest.mark.asyncio
async def test_rating_counts_finished_even_without_a_result(session: AsyncSession) -> None:
    """Uploading a Result is optional — CSV import alone marks someone `finished`,
    and that's enough to show up in the rating."""
    org = await make_user(session, "org@example.com", UserRole.organizer)
    runner = await make_user(session, "runner@example.com")
    _, group = await make_event_group(session, org)

    await _bare_attendance(session, group, runner, finish_status=FinishStatus.finished)
    await session.commit()

    assert await runner_finished_count(session, runner.id, "all") == 1
    rating = await compute_rating(session, "all")
    assert len(rating) == 1
    assert rating[0].runner_id == runner.id
    assert rating[0].finished_count == 1


@pytest.mark.asyncio
async def test_rating_counts_finished_with_pending_result(session: AsyncSession) -> None:
    """A Result still awaiting moderation doesn't change finish_status, so it keeps
    counting — moderation gates the displayed time/pace, not participation."""
    org = await make_user(session, "org1b@example.com", UserRole.organizer)
    runner = await make_user(session, "runner1b@example.com")
    _, group = await make_event_group(session, org)

    await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.pending,
    )
    await session.commit()

    assert await runner_finished_count(session, runner.id, "all") == 1


@pytest.mark.asyncio
async def test_rating_excludes_dnf(session: AsyncSession) -> None:
    org = await make_user(session, "org1c@example.com", UserRole.organizer)
    runner = await make_user(session, "runner1c@example.com")
    _, group = await make_event_group(session, org)

    await _bare_attendance(session, group, runner, finish_status=FinishStatus.dnf)
    await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.dnf,
        moderation=ModerationStatus.approved,
    )
    await session.commit()

    assert await runner_finished_count(session, runner.id, "all") == 0
    assert await compute_rating(session, "all") == []


@pytest.mark.asyncio
async def test_rating_ignores_unmatched_records(session: AsyncSession) -> None:
    org = await make_user(session, "org2@example.com", UserRole.organizer)
    _, group = await make_event_group(session, org)
    # Unmatched (runner_id None), finished -> still not counted.
    await make_attendance_with_result(
        session,
        group,
        None,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.approved,
    )
    await session.commit()

    rating = await compute_rating(session, "all")
    assert rating == []


@pytest.mark.asyncio
async def test_month_period_excludes_events_far_in_the_future(session: AsyncSession) -> None:
    """A group scheduled e.g. 3 months from now must NOT count towards "this
    month" just because its date is >= today - 30 days — the window needs an
    upper bound (today) too, not just a lower one."""
    org = await make_user(session, "org5@example.com", UserRole.organizer)
    runner = await make_user(session, "runner5@example.com")
    now = datetime.now(UTC)

    soon_event = Event(title="Soon", date=(now - timedelta(days=3)).date(), created_by=org.id)
    far_event = Event(title="Far", date=(now + timedelta(days=90)).date(), created_by=org.id)
    session.add_all([soon_event, far_event])
    await session.flush()

    soon_group = Group(
        event_id=soon_event.id, location="P", name="A", target_distance_km=10, start_time=now
    )
    far_group = Group(
        event_id=far_event.id, location="P", name="B", target_distance_km=10, start_time=now
    )
    session.add_all([soon_group, far_group])
    await session.flush()

    await _bare_attendance(session, soon_group, runner, finish_status=FinishStatus.finished)
    await _bare_attendance(session, far_group, runner, finish_status=FinishStatus.finished)
    await session.commit()

    assert await runner_finished_count(session, runner.id, "all") == 2
    # Only the near-term event falls inside the rolling 30-day "month" window.
    assert await runner_finished_count(session, runner.id, "month") == 1


@pytest.mark.asyncio
async def test_rating_excludes_groups_opted_out_of_rating(session: AsyncSession) -> None:
    """A social/kids group with counts_toward_rating=False shouldn't feed the
    rating even though its finishers are perfectly valid AttendanceRecords."""
    org = await make_user(session, "org-norating@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-norating@example.com")
    event, rated_group = await make_event_group(session, org)
    unrated_group = Group(
        event_id=event.id,
        location="Парк",
        name="Детский забег",
        target_distance_km=1,
        counts_toward_rating=False,
    )
    session.add(unrated_group)
    await session.flush()

    await _bare_attendance(session, rated_group, runner, finish_status=FinishStatus.finished)
    await _bare_attendance(session, unrated_group, runner, finish_status=FinishStatus.finished)
    await session.commit()

    assert await runner_finished_count(session, runner.id, "all") == 1
    rating = await compute_rating(session, "all")
    assert len(rating) == 1
    assert rating[0].finished_count == 1


@pytest.mark.asyncio
async def test_rating_orders_by_count_desc(session: AsyncSession) -> None:
    org = await make_user(session, "org3@example.com", UserRole.organizer)
    r1 = await make_user(session, "r1@example.com")
    r2 = await make_user(session, "r2@example.com")
    _, group = await make_event_group(session, org)

    for _ in range(2):
        await make_attendance_with_result(
            session,
            group,
            r1,
            finish_status=FinishStatus.finished,
            moderation=ModerationStatus.approved,
        )
    await make_attendance_with_result(
        session,
        group,
        r2,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.approved,
    )
    await session.commit()

    rating = await compute_rating(session, "all")
    assert [e.runner_id for e in rating] == [r1.id, r2.id]
    assert rating[0].finished_count == 2


@pytest.mark.asyncio
async def test_baseline_adds_to_all_time_rating_but_not_year_or_month(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-baseline1@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-baseline1@example.com")
    now = datetime.now(UTC)
    event = Event(title="DX Today", date=now.date(), created_by=org.id)
    session.add(event)
    await session.flush()
    group = Group(event_id=event.id, location="City", name="A", target_distance_km=10)
    session.add(group)
    await session.flush()
    await make_baseline(session, runner, dx_count=47)

    await _bare_attendance(session, group, runner, finish_status=FinishStatus.finished)
    await session.commit()

    assert await runner_finished_count(session, runner.id, "all") == 1 + 47
    assert await runner_finished_count(session, runner.id, "year") == 1
    assert await runner_finished_count(session, runner.id, "month") == 1

    rating = await compute_rating(session, "all")
    assert rating[0].finished_count == 1 + 47
    year_rating = await compute_rating(session, "year")
    assert year_rating[0].finished_count == 1


@pytest.mark.asyncio
async def test_baseline_only_runner_still_appears_in_all_time_rating(
    session: AsyncSession,
) -> None:
    """A veteran runner might have a carry-over count but zero attendance
    tracked by this app yet — they should still show up in the all-time
    rating, not just runners already in AttendanceRecord data."""
    runner = await make_user(session, "runner-baseline2@example.com")
    await make_baseline(session, runner, dx_count=100)
    await session.commit()

    assert await runner_finished_count(session, runner.id, "all") == 100
    assert await runner_finished_count(session, runner.id, "year") == 0

    rating = await compute_rating(session, "all")
    assert len(rating) == 1
    assert rating[0].runner_id == runner.id
    assert rating[0].finished_count == 100
    assert await compute_rating(session, "year") == []


async def _event_group(
    session: AsyncSession,
    org,
    when,
    target_km: float,
    runner,
    *,
    finish_status=FinishStatus.finished,
) -> None:
    event = Event(title=f"DX {when.isoformat()}", date=when, created_by=org.id)
    session.add(event)
    await session.flush()
    group = Group(event_id=event.id, location="City", name="A", target_distance_km=target_km)
    session.add(group)
    await session.flush()
    await _bare_attendance(session, group, runner, finish_status=finish_status)


@pytest.mark.asyncio
async def test_month_tie_breaks_on_km_this_month(session: AsyncSession) -> None:
    org = await make_user(session, "org-tie1@example.com", UserRole.organizer)
    r1 = await make_user(session, "r1-tie1@example.com")
    r2 = await make_user(session, "r2-tie1@example.com")
    today = datetime.now(UTC).date()

    await _event_group(session, org, today, 30, r1)  # same finishes_month (1 each)
    await _event_group(session, org, today, 10, r2)  # but r1 ran further
    await session.commit()

    rating = await compute_rating(session, "month")
    assert [e.runner_id for e in rating] == [r1.id, r2.id]
    assert rating[0].finished_count == rating[1].finished_count == 1


@pytest.mark.asyncio
async def test_month_tie_cascades_to_finishes_this_year(session: AsyncSession) -> None:
    org = await make_user(session, "org-tie2@example.com", UserRole.organizer)
    r1 = await make_user(session, "r1-tie2@example.com")
    r2 = await make_user(session, "r2-tie2@example.com")
    today = datetime.now(UTC).date()
    two_months_ago = today - timedelta(days=60)

    # Both tied at month level (1 finish, 10km) -> r1 has an extra finish
    # earlier this year (outside the rolling month window) to win on the
    # next cascade level (finishes_year).
    await _event_group(session, org, today, 10, r1)
    await _event_group(session, org, two_months_ago, 10, r1)
    await _event_group(session, org, today, 10, r2)
    await session.commit()

    rating = await compute_rating(session, "month")
    assert [e.runner_id for e in rating] == [r1.id, r2.id]
    # The displayed count is still just this month's, unaffected by the tiebreak.
    assert rating[0].finished_count == 1
    assert rating[1].finished_count == 1


@pytest.mark.asyncio
async def test_month_tie_cascades_all_the_way_to_finishes_all_time(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-tie3@example.com", UserRole.organizer)
    r1 = await make_user(session, "r1-tie3@example.com")
    r2 = await make_user(session, "r2-tie3@example.com")
    today = datetime.now(UTC).date()
    two_years_ago = today - timedelta(days=730)

    # Tied on month (1/10km) and year (1/10km) -> r1 has an extra finish
    # outside the rolling year window to win on finishes_all.
    await _event_group(session, org, today, 10, r1)
    await _event_group(session, org, two_years_ago, 5, r1)
    await _event_group(session, org, today, 10, r2)
    await session.commit()

    rating = await compute_rating(session, "month")
    assert [e.runner_id for e in rating] == [r1.id, r2.id]


@pytest.mark.asyncio
async def test_year_tie_breaks_on_km_this_year_then_finishes_all(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-tie4@example.com", UserRole.organizer)
    r1 = await make_user(session, "r1-tie4@example.com")
    r2 = await make_user(session, "r2-tie4@example.com")
    today = datetime.now(UTC).date()

    await _event_group(session, org, today, 30, r1)
    await _event_group(session, org, today, 10, r2)
    await session.commit()

    rating = await compute_rating(session, "year")
    assert [e.runner_id for e in rating] == [r1.id, r2.id]


@pytest.mark.asyncio
async def test_all_time_tie_breaks_on_km(session: AsyncSession) -> None:
    org = await make_user(session, "org-tie5@example.com", UserRole.organizer)
    r1 = await make_user(session, "r1-tie5@example.com")
    r2 = await make_user(session, "r2-tie5@example.com")
    today = datetime.now(UTC).date()

    await _event_group(session, org, today, 30, r1)
    await _event_group(session, org, today, 10, r2)
    await session.commit()

    rating = await compute_rating(session, "all")
    assert [e.runner_id for e in rating] == [r1.id, r2.id]
