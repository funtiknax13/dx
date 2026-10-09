from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import ClaimStatus, FinishStatus, ModerationStatus, ResultSource, UserRole
from app.models.group import Group
from app.models.guest_claim import GuestClaim
from app.models.result import Result
from app.models.runner_baseline import RunnerBaseline
from app.models.user import User
from app.services.guest_service import (
    create_guest,
    merge_guest_into,
    move_baseline_to_guest,
    split_name,
)
from tests.factories import make_baseline, make_event_group, make_user


def test_split_name() -> None:
    assert split_name("Alice Runner") == ("Alice", "Runner")
    assert split_name("Cher") == ("Cher", "")
    assert split_name("  Alice   Van Runner  ") == ("Alice", "Van Runner")


@pytest.mark.asyncio
async def test_create_guest_has_synthetic_credentials(session: AsyncSession) -> None:
    guest = await create_guest(session, "Alice Runner")
    assert guest.is_guest is True
    assert guest.first_name == "Alice"
    assert guest.last_name == "Runner"
    assert guest.email.endswith("@dh.guest")
    assert guest.role == UserRole.runner


@pytest.mark.asyncio
async def test_merge_guest_into_reassigns_attendance(session: AsyncSession) -> None:
    org = await make_user(session, "org@example.com", UserRole.organizer)
    real_user = await make_user(session, "real@example.com")
    _, group = await make_event_group(session, org)
    guest = await create_guest(session, "Alice Runner")

    rec = AttendanceRecord(
        group_id=group.id,
        raw_name="Alice Runner",
        runner_id=guest.id,
        finish_status=FinishStatus.finished,
    )
    session.add(rec)
    await session.flush()

    await merge_guest_into(session, guest, real_user)
    await session.commit()

    await session.refresh(rec)
    await session.refresh(guest)
    assert rec.runner_id == real_user.id
    assert guest.merged_into_id == real_user.id
    assert guest.is_guest is True  # kept for audit, per product decision


@pytest.mark.asyncio
async def test_merge_guest_into_reconciles_a_duplicate_event_participation(
    session: AsyncSession,
) -> None:
    """A runner who self-reported a result *before* ever being claimed from
    a guest profile (e.g. a later CSV import for the same event created the
    guest, under a different distance group) must not end up with two
    AttendanceRecords for the same event after the merge — the guest's
    CSV-sourced finish_status/group win (a guest can never have self-
    reported itself), but the account's own already-uploaded Result is kept."""
    org = await make_user(session, "org-reconcile@example.com", UserRole.organizer)
    real_user = await make_user(session, "real-reconcile@example.com")
    _, group_a = await make_event_group(session, org, target_km=21.0)
    group_b = Group(
        event_id=group_a.event_id, location="City", name="X-30", target_distance_km=30.0
    )
    session.add(group_b)
    await session.flush()

    own_record = AttendanceRecord(
        group_id=group_a.id,
        raw_name="Иван Самоотчёт",
        runner_id=real_user.id,
        finish_status=FinishStatus.finished,
        self_reported=True,
    )
    session.add(own_record)
    await session.flush()
    own_result = Result(
        attendance_record_id=own_record.id,
        distance_km=21.0,
        duration_seconds=6000,
        pace_seconds_per_km=285.7,
        source=ResultSource.manual,
        finish_status=FinishStatus.finished,
        status=ModerationStatus.approved,
    )
    session.add(own_result)
    own_record_id = own_record.id

    guest = await create_guest(session, "Иван Самоотчётов")
    guest_record = AttendanceRecord(
        group_id=group_b.id,
        raw_name="Иван Самоотчётов",
        runner_id=guest.id,
        finish_status=FinishStatus.dnf,
    )
    session.add(guest_record)
    await session.flush()
    guest_record_id = guest_record.id

    await merge_guest_into(session, guest, real_user)
    await session.commit()

    remaining = list(
        await session.scalars(
            select(AttendanceRecord).where(AttendanceRecord.runner_id == real_user.id)
        )
    )
    assert len(remaining) == 1
    merged = remaining[0]
    assert merged.id == own_record_id  # the account's own record survives, not a new one
    assert merged.group_id == group_b.id  # CSV's (guest's) group placement wins
    assert merged.finish_status == FinishStatus.dnf  # CSV's finish_status wins
    assert merged.self_reported is False

    # The guest's own record is gone — not left behind as a second row.
    assert await session.get(AttendanceRecord, guest_record_id) is None

    # The account's own uploaded Result survives untouched (distance/pace/
    # moderation), only its finish_status is kept in sync.
    result = await session.scalar(
        select(Result).where(Result.attendance_record_id == own_record_id)
    )
    assert result is not None
    assert result.distance_km == 21.0
    assert result.duration_seconds == 6000
    assert result.status == ModerationStatus.approved
    assert result.finish_status == FinishStatus.dnf


@pytest.mark.asyncio
async def test_merge_guest_into_rejects_other_pending_claims(session: AsyncSession) -> None:
    org = await make_user(session, "org2@example.com", UserRole.organizer)
    winner = await make_user(session, "winner@example.com")
    loser = await make_user(session, "loser@example.com")
    await make_event_group(session, org)
    guest = await create_guest(session, "Alice Runner")

    claim_winner = GuestClaim(guest_user_id=guest.id, claimant_user_id=winner.id)
    claim_loser = GuestClaim(guest_user_id=guest.id, claimant_user_id=loser.id)
    session.add_all([claim_winner, claim_loser])
    await session.flush()

    await merge_guest_into(session, guest, winner)
    await session.commit()

    await session.refresh(claim_loser)
    assert claim_loser.status == ClaimStatus.rejected
    assert claim_loser.decided_at is not None


@pytest.mark.asyncio
async def test_merge_guest_into_rejects_non_guest(session: AsyncSession) -> None:
    real_a = await make_user(session, "a@example.com")
    real_b = await make_user(session, "b@example.com")
    with pytest.raises(ValueError):
        await merge_guest_into(session, real_a, real_b)


@pytest.mark.asyncio
async def test_merge_guest_into_moves_signups_and_drops_collisions(
    session: AsyncSession,
) -> None:
    from app.models.signup import Signup

    org = await make_user(session, "org3@example.com", UserRole.organizer)
    real_user = await make_user(session, "real3@example.com")
    _, group = await make_event_group(session, org)
    guest = await create_guest(session, "Bob Runner")

    session.add(Signup(runner_id=guest.id, group_id=group.id, event_id=group.event_id))
    session.add(Signup(runner_id=real_user.id, group_id=group.id, event_id=group.event_id))
    await session.flush()

    await merge_guest_into(session, guest, real_user)
    await session.commit()

    signups = list(await session.scalars(select(Signup).where(Signup.group_id == group.id)))
    # The guest's duplicate signup for the same group was dropped, not duplicated.
    assert len(signups) == 1
    assert signups[0].runner_id == real_user.id


@pytest.mark.asyncio
async def test_merge_guest_into_moves_baseline_when_real_user_has_none(
    session: AsyncSession,
) -> None:
    real_user = await make_user(session, "real-base1@example.com")
    guest = await create_guest(session, "Carol Runner")
    await make_baseline(session, guest, dx_count=47, total_runs=50, total_km=623.5)

    await merge_guest_into(session, guest, real_user)
    await session.commit()

    moved = await session.scalar(
        select(RunnerBaseline).where(RunnerBaseline.runner_id == real_user.id)
    )
    assert moved is not None
    assert moved.dx_count == 47
    assert (
        await session.scalar(select(RunnerBaseline).where(RunnerBaseline.runner_id == guest.id))
        is None
    )


@pytest.mark.asyncio
async def test_merge_guest_into_sums_baseline_when_real_user_already_has_one(
    session: AsyncSession,
) -> None:
    real_user = await make_user(session, "real-base2@example.com")
    guest = await create_guest(session, "Dave Runner")
    await make_baseline(session, real_user, dx_count=10, total_runs=12, total_km=100.0)
    await make_baseline(session, guest, dx_count=5, total_runs=6, total_km=50.0)

    await merge_guest_into(session, guest, real_user)
    await session.commit()

    real_baseline = await session.scalar(
        select(RunnerBaseline).where(RunnerBaseline.runner_id == real_user.id)
    )
    assert real_baseline is not None
    assert real_baseline.dx_count == 15
    assert real_baseline.total_runs == 18
    assert real_baseline.total_km == 150.0
    assert (
        await session.scalar(select(RunnerBaseline).where(RunnerBaseline.runner_id == guest.id))
        is None
    )


@pytest.mark.asyncio
async def test_merge_guest_into_keeps_the_earlier_first_run_date(
    session: AsyncSession,
) -> None:
    real_user = await make_user(session, "real-base3@example.com")
    guest = await create_guest(session, "Erin Runner")
    await make_baseline(session, real_user, first_run_date=date(2020, 1, 1))
    await make_baseline(session, guest, first_run_date=date(2018, 6, 15))

    await merge_guest_into(session, guest, real_user)
    await session.commit()

    real_baseline = await session.scalar(
        select(RunnerBaseline).where(RunnerBaseline.runner_id == real_user.id)
    )
    assert real_baseline is not None
    assert real_baseline.first_run_date == date(2018, 6, 15)  # earlier of the two wins


@pytest.mark.asyncio
async def test_merge_guest_into_sums_this_year_baseline_when_years_match(
    session: AsyncSession,
) -> None:
    real_user = await make_user(session, "real-baseyear1@example.com")
    guest = await create_guest(session, "Fay Runner")
    await make_baseline(
        session, real_user, dx_count_this_year=10, km_this_year=100.0, baseline_year=2026
    )
    await make_baseline(session, guest, dx_count_this_year=5, km_this_year=50.0, baseline_year=2026)

    await merge_guest_into(session, guest, real_user)
    await session.commit()

    real_baseline = await session.scalar(
        select(RunnerBaseline).where(RunnerBaseline.runner_id == real_user.id)
    )
    assert real_baseline is not None
    assert real_baseline.dx_count_this_year == 15
    assert real_baseline.km_this_year == 150.0
    assert real_baseline.baseline_year == 2026


@pytest.mark.asyncio
async def test_merge_guest_into_adopts_this_year_baseline_when_target_has_none(
    session: AsyncSession,
) -> None:
    """The target has a baseline (so it doesn't just get replaced wholesale),
    but no year-figures set yet -> the source's year-figures should carry
    over rather than being silently dropped."""
    real_user = await make_user(session, "real-baseyear2@example.com")
    guest = await create_guest(session, "Gia Runner")
    await make_baseline(session, real_user, dx_count=10)
    await make_baseline(
        session, guest, dx_count=5, dx_count_this_year=5, km_this_year=50.0, baseline_year=2026
    )

    await merge_guest_into(session, guest, real_user)
    await session.commit()

    real_baseline = await session.scalar(
        select(RunnerBaseline).where(RunnerBaseline.runner_id == real_user.id)
    )
    assert real_baseline is not None
    assert real_baseline.dx_count_this_year == 5
    assert real_baseline.km_this_year == 50.0
    assert real_baseline.baseline_year == 2026


@pytest.mark.asyncio
async def test_merge_guest_into_drops_mismatched_year_baseline(
    session: AsyncSession,
) -> None:
    """The target already has its own year-figures for a *different* year
    than the source -> the source's figures describe a year that isn't
    "current" for this merged baseline and can't be safely combined, so they
    are dropped rather than summed or overwriting the target's."""
    real_user = await make_user(session, "real-baseyear3@example.com")
    guest = await create_guest(session, "Hana Runner")
    await make_baseline(
        session, real_user, dx_count_this_year=10, km_this_year=100.0, baseline_year=2026
    )
    await make_baseline(session, guest, dx_count_this_year=5, km_this_year=50.0, baseline_year=2025)

    await merge_guest_into(session, guest, real_user)
    await session.commit()

    real_baseline = await session.scalar(
        select(RunnerBaseline).where(RunnerBaseline.runner_id == real_user.id)
    )
    assert real_baseline is not None
    assert real_baseline.dx_count_this_year == 10
    assert real_baseline.km_this_year == 100.0
    assert real_baseline.baseline_year == 2026


@pytest.mark.asyncio
async def test_move_baseline_to_guest_is_a_no_op_without_a_baseline(
    session: AsyncSession,
) -> None:
    real_user = await make_user(session, "no-baseline@example.com")
    await session.commit()

    await move_baseline_to_guest(session, real_user)
    await session.commit()

    assert await session.scalar(select(User).where(User.is_guest.is_(True))) is None


@pytest.mark.asyncio
async def test_move_baseline_to_guest_creates_a_fresh_guest(session: AsyncSession) -> None:
    real_user = await make_user(session, "has-baseline@example.com")
    real_user.first_name, real_user.last_name = "Eve", "Baseline"
    await make_baseline(session, real_user, dx_count=47, total_runs=50, total_km=623.5)
    await session.commit()

    await move_baseline_to_guest(session, real_user)
    await session.commit()

    guest = await session.scalar(
        select(User).where(
            User.is_guest.is_(True), User.first_name == "Eve", User.last_name == "Baseline"
        )
    )
    assert guest is not None
    guest_baseline = await session.scalar(
        select(RunnerBaseline).where(RunnerBaseline.runner_id == guest.id)
    )
    assert guest_baseline is not None
    assert guest_baseline.dx_count == 47
    assert (
        await session.scalar(select(RunnerBaseline).where(RunnerBaseline.runner_id == real_user.id))
        is None
    )


@pytest.mark.asyncio
async def test_move_baseline_to_guest_reuses_existing_unmerged_guest(
    session: AsyncSession,
) -> None:
    real_user = await make_user(session, "has-baseline2@example.com")
    real_user.first_name, real_user.last_name = "Frank", "Baseline"
    await make_baseline(session, real_user, dx_count=10)
    existing_guest = await create_guest(session, "Frank Baseline")
    await make_baseline(session, existing_guest, dx_count=5)
    await session.commit()

    await move_baseline_to_guest(session, real_user)
    await session.commit()

    guest_baseline = await session.scalar(
        select(RunnerBaseline).where(RunnerBaseline.runner_id == existing_guest.id)
    )
    assert guest_baseline is not None
    assert guest_baseline.dx_count == 15  # summed, not overwritten


@pytest.mark.asyncio
async def test_move_baseline_to_guest_falls_back_when_matched_guest_is_self(
    session: AsyncSession,
) -> None:
    """If a same-named guest was already merged into this very account, the
    name-resolution would otherwise point right back at the account being
    deleted — must fall back to a brand-new guest instead of a no-op."""
    real_user = await make_user(session, "has-baseline3@example.com")
    real_user.first_name, real_user.last_name = "Grace", "Baseline"
    already_merged_guest = await create_guest(session, "Grace Baseline")
    await merge_guest_into(session, already_merged_guest, real_user)
    await make_baseline(session, real_user, dx_count=10)
    await session.commit()

    await move_baseline_to_guest(session, real_user)
    await session.commit()

    fresh_guests = list(
        await session.scalars(
            select(User).where(
                User.is_guest.is_(True),
                User.first_name == "Grace",
                User.last_name == "Baseline",
                User.id != already_merged_guest.id,
            )
        )
    )
    assert len(fresh_guests) == 1
    fresh_baseline = await session.scalar(
        select(RunnerBaseline).where(RunnerBaseline.runner_id == fresh_guests[0].id)
    )
    assert fresh_baseline is not None
    assert fresh_baseline.dx_count == 10
