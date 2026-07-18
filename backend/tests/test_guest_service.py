from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import ClaimStatus, FinishStatus, UserRole
from app.models.guest_claim import GuestClaim
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
