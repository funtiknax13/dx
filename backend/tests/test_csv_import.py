import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, UserRole
from app.models.user import User
from app.services.csv_import_service import import_attendance_csv
from tests.factories import make_event_group, make_user

CSV = """full_name;email;phone
Alice Runner;alice@example.com;+100
Bob Runner;bob@example.com;
Alice Runner;dup@example.com;+999
;;
Carol Runner;;
"""

CSV_WITH_RESULT = """full_name;email;result
Dana Runner;dana@example.com;1
Erin Runner;erin@example.com;0
Frank Runner;frank@example.com;
"""


@pytest.mark.asyncio
async def test_csv_import_creates_finished_records_and_dedupes(session: AsyncSession) -> None:
    org = await make_user(session, "org@example.com", UserRole.organizer)
    _, group = await make_event_group(session, org)

    result = await import_attendance_csv(session, group.id, CSV)
    await session.commit()

    assert result.created_count == 3  # Alice, Bob, Carol
    assert result.skipped_duplicates == 1  # second Alice
    assert result.skipped_empty == 1  # blank row
    # None of these emails match a registered account -> every row becomes a guest.
    assert result.auto_matched == 0
    assert result.guests_created == 3

    records = list(
        await session.scalars(
            select(AttendanceRecord).where(AttendanceRecord.group_id == group.id)
        )
    )
    assert len(records) == 3
    assert all(r.finish_status == FinishStatus.finished for r in records)
    # Every record is linked to *some* account right away (real match or guest) —
    # nothing sits unmatched, so it shows up in the protocol immediately.
    assert all(r.runner_id is not None for r in records)
    alice = next(r for r in records if r.raw_name == "Alice Runner")
    assert alice.raw_email == "alice@example.com"
    assert alice.raw_phone == "+100"

    guest = await session.get(User, alice.runner_id)
    assert guest is not None
    assert guest.is_guest is True
    assert guest.first_name == "Alice"
    assert guest.last_name == "Runner"


@pytest.mark.asyncio
async def test_csv_email_auto_matches_registered_account(session: AsyncSession) -> None:
    org = await make_user(session, "org1b@example.com", UserRole.organizer)
    runner = await make_user(session, "alice@example.com")
    _, group = await make_event_group(session, org)

    result = await import_attendance_csv(session, group.id, CSV)
    await session.commit()

    assert result.auto_matched == 1  # Alice's email matches the registered runner
    assert result.guests_created == 2  # Bob, Carol

    alice_record = await session.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.group_id == group.id, AttendanceRecord.raw_name == "Alice Runner"
        )
    )
    assert alice_record is not None
    assert alice_record.runner_id == runner.id


@pytest.mark.asyncio
async def test_csv_import_reuses_existing_guest_by_name(session: AsyncSession) -> None:
    org = await make_user(session, "org1c@example.com", UserRole.organizer)
    _, group_a = await make_event_group(session, org)
    _, group_b = await make_event_group(session, org)

    first = await import_attendance_csv(session, group_a.id, "full_name;email\nBob Runner;\n")
    await session.commit()
    second = await import_attendance_csv(session, group_b.id, "full_name;email\nBob Runner;\n")
    await session.commit()

    assert first.guests_created == 1
    assert second.guests_created == 0
    assert second.guests_reused == 1  # same "Bob Runner" -> same guest, not a duplicate

    rec_a = await session.scalar(
        select(AttendanceRecord).where(AttendanceRecord.group_id == group_a.id)
    )
    rec_b = await session.scalar(
        select(AttendanceRecord).where(AttendanceRecord.group_id == group_b.id)
    )
    assert rec_a is not None and rec_b is not None
    assert rec_a.runner_id == rec_b.runner_id


@pytest.mark.asyncio
async def test_csv_import_redirects_to_merged_account_by_name(session: AsyncSession) -> None:
    from app.services.guest_service import create_guest, merge_guest_into

    org = await make_user(session, "org1d@example.com", UserRole.organizer)
    real_user = await make_user(session, "realbob@example.com")
    _, group_a = await make_event_group(session, org)
    _, group_b = await make_event_group(session, org)

    guest = await create_guest(session, "Bob Runner")
    await merge_guest_into(session, guest, real_user)
    await session.commit()

    # A later import of the same name (no email) should resolve straight to the
    # real account — no second guest, no new claim needed.
    result = await import_attendance_csv(session, group_a.id, "full_name;email\nBob Runner;\n")
    await session.commit()

    assert result.merged_redirects == 1
    assert result.guests_created == 0
    assert result.guests_reused == 0

    rec = await session.scalar(
        select(AttendanceRecord).where(AttendanceRecord.group_id == group_a.id)
    )
    assert rec is not None
    assert rec.runner_id == real_user.id


@pytest.mark.asyncio
async def test_reimport_is_idempotent(session: AsyncSession) -> None:
    org = await make_user(session, "org2@example.com", UserRole.organizer)
    _, group = await make_event_group(session, org)

    await import_attendance_csv(session, group.id, CSV)
    await session.commit()
    second = await import_attendance_csv(session, group.id, CSV)
    await session.commit()

    assert second.created_count == 0
    # All 4 non-empty rows (incl. the in-file duplicate Alice) now collide with existing.
    assert second.skipped_duplicates == 4
    assert second.guests_created == 0


@pytest.mark.asyncio
async def test_csv_missing_required_column_raises(session: AsyncSession) -> None:
    org = await make_user(session, "org3@example.com", UserRole.organizer)
    _, group = await make_event_group(session, org)
    with pytest.raises(ValueError):
        await import_attendance_csv(session, group.id, "name;email\nx;y\n")


@pytest.mark.asyncio
async def test_result_column_zero_marks_dnf(session: AsyncSession) -> None:
    org = await make_user(session, "org4@example.com", UserRole.organizer)
    _, group = await make_event_group(session, org)

    result = await import_attendance_csv(session, group.id, CSV_WITH_RESULT)
    await session.commit()

    assert result.created_count == 3
    records = {
        r.raw_name: r
        for r in await session.scalars(
            select(AttendanceRecord).where(AttendanceRecord.group_id == group.id)
        )
    }
    assert records["Dana Runner"].finish_status == FinishStatus.finished
    assert records["Erin Runner"].finish_status == FinishStatus.dnf
    # Blank result cell falls back to finished, same as no `result` column at all.
    assert records["Frank Runner"].finish_status == FinishStatus.finished
