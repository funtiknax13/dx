import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, UserRole
from app.models.group import Group
from app.models.user import User
from app.services.csv_import_service import import_attendance_csv
from tests.factories import make_event_group, make_user


async def _tagged_event(session: AsyncSession, org: User) -> tuple[int, Group, Group]:
    """An event with two distinctly-tagged groups: X-33 and D-25."""
    event, x_group = await make_event_group(session, org, target_km=33)
    x_group.distance_code = "X-33"
    d_group = Group(
        event_id=event.id, location="City", name="D-25", target_distance_km=25, distance_code="D-25"
    )
    session.add(d_group)
    await session.flush()
    return event.id, x_group, d_group


CSV = """first_name;last_name;email;phone;result
Alice;Runner;alice@example.com;+100;X
Bob;Runner;bob@example.com;;D
Alice;Runner;dup@example.com;+999;X
;;;;
Carol;Runner;;;Xn
"""


@pytest.mark.asyncio
async def test_csv_import_routes_by_tag_and_dedupes(session: AsyncSession) -> None:
    org = await make_user(session, "org@example.com", UserRole.organizer)
    event_id, x_group, d_group = await _tagged_event(session, org)

    result = await import_attendance_csv(session, event_id, CSV)
    await session.commit()

    assert result.created_count == 3  # Alice(X), Bob(D), Carol(X)
    assert result.skipped_duplicates == 1  # second Alice
    assert result.skipped_empty == 1  # blank row
    assert result.fallback_used is False

    x_records = list(
        await session.scalars(
            select(AttendanceRecord).where(AttendanceRecord.group_id == x_group.id)
        )
    )
    d_records = list(
        await session.scalars(
            select(AttendanceRecord).where(AttendanceRecord.group_id == d_group.id)
        )
    )
    assert {r.raw_name for r in x_records} == {"Alice Runner", "Carol Runner"}
    assert {r.raw_name for r in d_records} == {"Bob Runner"}

    alice = next(r for r in x_records if r.raw_name == "Alice Runner")
    assert alice.finish_status == FinishStatus.finished
    carol = next(r for r in x_records if r.raw_name == "Carol Runner")
    assert carol.finish_status == FinishStatus.dnf


@pytest.mark.asyncio
async def test_csv_import_skips_empty_result_cell(session: AsyncSession) -> None:
    org = await make_user(session, "org-notag@example.com", UserRole.organizer)
    event_id, x_group, _ = await _tagged_event(session, org)

    result = await import_attendance_csv(
        session, event_id, "first_name;last_name;result\nDave;Runner;\n"
    )
    await session.commit()

    assert result.created_count == 0
    assert result.skipped_no_tag == 1


@pytest.mark.asyncio
async def test_csv_import_skips_unmatched_tag(session: AsyncSession) -> None:
    org = await make_user(session, "org-unmatched@example.com", UserRole.organizer)
    event_id, x_group, _ = await _tagged_event(session, org)

    result = await import_attendance_csv(
        session, event_id, "first_name;last_name;result\nEva;Runner;P\n"
    )
    await session.commit()

    assert result.created_count == 0
    assert result.skipped_unmatched_tag == 1


@pytest.mark.asyncio
async def test_csv_import_normalizes_cyrillic_tag_letter(session: AsyncSession) -> None:
    """A group tagged with a Latin "X-33" must still match a CSV row whose tag
    letter was typed as the visually-identical Cyrillic "Х", and vice versa."""
    org = await make_user(session, "org-cyr@example.com", UserRole.organizer)
    event_id, x_group, _ = await _tagged_event(session, org)

    result = await import_attendance_csv(
        session,
        event_id,
        "first_name;last_name;result\nFrank;Runner;Х\n",  # Cyrillic Х
    )
    await session.commit()

    assert result.created_count == 1
    assert result.skipped_unmatched_tag == 0
    rec = await session.scalar(
        select(AttendanceRecord).where(AttendanceRecord.group_id == x_group.id)
    )
    assert rec is not None and rec.raw_name == "Frank Runner"


@pytest.mark.asyncio
async def test_csv_import_normalizes_cyrillic_er_to_latin_p(session: AsyncSession) -> None:
    """"Р" (Cyrillic Er) looks identical to "P" (Latin) — a group tagged with
    either script must match a CSV row tagged with either script."""
    org = await make_user(session, "org-per@example.com", UserRole.organizer)
    event, _ = await make_event_group(session, org, target_km=10)
    p_group = Group(
        event_id=event.id,
        location="City",
        name="Р-10",
        target_distance_km=10,
        distance_code="Р-10",  # Cyrillic Р in the group's own tag
    )
    session.add(p_group)
    await session.flush()

    result = await import_attendance_csv(
        session,
        event.id,
        "first_name;last_name;result\nGreg;Runner;P\n",  # Latin P in the CSV
    )
    await session.commit()

    assert result.created_count == 1
    assert result.skipped_unmatched_tag == 0
    rec = await session.scalar(
        select(AttendanceRecord).where(AttendanceRecord.group_id == p_group.id)
    )
    assert rec is not None and rec.raw_name == "Greg Runner"


@pytest.mark.asyncio
async def test_csv_import_falls_back_to_first_group_without_any_tags(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-fallback@example.com", UserRole.organizer)
    event, group = await make_event_group(session, org, target_km=10)
    assert group.distance_code is None

    result = await import_attendance_csv(
        session,
        event.id,
        "first_name;last_name;result\nGrace;Runner;X\nHank;Runner;Zn\n",
    )
    await session.commit()

    assert result.fallback_used is True
    assert result.created_count == 2
    records = list(
        await session.scalars(select(AttendanceRecord).where(AttendanceRecord.group_id == group.id))
    )
    assert {r.raw_name for r in records} == {"Grace Runner", "Hank Runner"}
    grace = next(r for r in records if r.raw_name == "Grace Runner")
    hank = next(r for r in records if r.raw_name == "Hank Runner")
    assert grace.finish_status == FinishStatus.finished
    assert hank.finish_status == FinishStatus.dnf


@pytest.mark.asyncio
async def test_csv_import_shared_tag_routes_to_lowest_id_group(session: AsyncSession) -> None:
    """Two pace-subgroups sharing one distance_code (already sharing one merged
    protocol) both match the same tag letter — the row lands on whichever of
    them has the lower id, deterministically."""
    org = await make_user(session, "org-shared@example.com", UserRole.organizer)
    event, group1 = await make_event_group(session, org, target_km=33)
    group1.distance_code = "X-33"
    group2 = Group(
        event_id=event.id,
        location="City",
        name="X-33 #2",
        target_distance_km=33,
        distance_code="X-33",
    )
    session.add(group2)
    await session.flush()

    result = await import_attendance_csv(
        session, event.id, "first_name;last_name;result\nIvy;Runner;X\n"
    )
    await session.commit()

    assert result.created_count == 1
    rec = await session.scalar(select(AttendanceRecord))
    assert rec is not None
    assert rec.group_id == min(group1.id, group2.id)


@pytest.mark.asyncio
async def test_csv_import_reuses_existing_guest_by_name(session: AsyncSession) -> None:
    org = await make_user(session, "org-guest@example.com", UserRole.organizer)
    event_id, x_group, _ = await _tagged_event(session, org)

    first = await import_attendance_csv(
        session, event_id, "first_name;last_name;result\nBob;Runner;X\n"
    )
    await session.commit()
    second = await import_attendance_csv(
        session, event_id, "first_name;last_name;result\nBob;Runner;X\n"
    )
    await session.commit()

    assert first.guests_created == 1
    assert second.created_count == 0
    assert second.skipped_duplicates == 1


@pytest.mark.asyncio
async def test_csv_import_email_auto_matches_registered_account(session: AsyncSession) -> None:
    org = await make_user(session, "org-email@example.com", UserRole.organizer)
    runner = await make_user(session, "known@example.com")
    event_id, x_group, _ = await _tagged_event(session, org)

    result = await import_attendance_csv(
        session, event_id, "first_name;last_name;email;result\nKnown;Runner;known@example.com;X\n"
    )
    await session.commit()

    assert result.auto_matched == 1
    rec = await session.scalar(
        select(AttendanceRecord).where(AttendanceRecord.group_id == x_group.id)
    )
    assert rec is not None
    assert rec.runner_id == runner.id


@pytest.mark.asyncio
async def test_csv_import_flags_email_mismatch_within_same_import(
    session: AsyncSession,
) -> None:
    """Two different rows with the same name but different emails, going to
    different groups in the same event — likely two different people, not a
    duplicate of one. The second row still imports (attached to the guest the
    first one created, since name-matching can't tell them apart), but is
    flagged for admin review."""
    org = await make_user(session, "org-mismatch1@example.com", UserRole.organizer)
    event_id, x_group, d_group = await _tagged_event(session, org)

    result = await import_attendance_csv(
        session,
        event_id,
        "first_name;last_name;email;result\n"
        "Ivan;Petrov;ivan1@example.com;X\n"
        "Ivan;Petrov;ivan2@example.com;D\n",
    )
    await session.commit()

    assert result.created_count == 2
    assert result.guests_created == 1
    assert result.guests_reused == 1
    assert len(result.email_mismatches) == 1
    mismatch = result.email_mismatches[0]
    assert mismatch.raw_name == "Ivan Petrov"
    assert mismatch.row_email == "ivan2@example.com"
    assert mismatch.known_email == "ivan1@example.com"

    # Both rows still land on the same (single) guest account — the point is
    # to flag the collision, not to silently split it into two accounts.
    records = list(await session.scalars(select(AttendanceRecord)))
    assert len({r.runner_id for r in records}) == 1


@pytest.mark.asyncio
async def test_csv_import_flags_email_mismatch_across_separate_imports(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-mismatch2@example.com", UserRole.organizer)
    event_id, x_group, _ = await _tagged_event(session, org)

    first = await import_attendance_csv(
        session, event_id, "first_name;last_name;email;result\nAnna;Orlova;anna1@example.com;X\n"
    )
    await session.commit()
    assert first.email_mismatches == []

    second_event_id, _, _ = await _tagged_event(session, org)
    second = await import_attendance_csv(
        session,
        second_event_id,
        "first_name;last_name;email;result\nAnna;Orlova;anna2@example.com;X\n",
    )
    await session.commit()

    assert len(second.email_mismatches) == 1
    assert second.email_mismatches[0].known_email == "anna1@example.com"
    assert second.email_mismatches[0].row_email == "anna2@example.com"


@pytest.mark.asyncio
async def test_csv_import_no_mismatch_when_email_matches_known(session: AsyncSession) -> None:
    org = await make_user(session, "org-mismatch3@example.com", UserRole.organizer)
    event_id, x_group, _ = await _tagged_event(session, org)

    await import_attendance_csv(
        session, event_id, "first_name;last_name;email;result\nDan;Orlov;dan@example.com;X\n"
    )
    await session.commit()

    second_event_id, _, _ = await _tagged_event(session, org)
    result = await import_attendance_csv(
        session,
        second_event_id,
        "first_name;last_name;email;result\nDan;Orlov;dan@example.com;X\n",
    )
    await session.commit()

    assert result.email_mismatches == []
    assert result.guests_reused == 1


@pytest.mark.asyncio
async def test_csv_import_flags_email_mismatch_on_merge_redirect(session: AsyncSession) -> None:
    from app.services.guest_service import create_guest, merge_guest_into

    org = await make_user(session, "org-mismatch4@example.com", UserRole.organizer)
    real_user = await make_user(session, "real-mismatch4@example.com")
    guest = await create_guest(session, "Olga Titova")
    event_id, x_group, _ = await _tagged_event(session, org)
    # Give the guest a tracked attendance with a known email before merging,
    # so there's something on file for the real account to be compared
    # against once the merge reassigns it.
    session.add(
        AttendanceRecord(
            group_id=x_group.id,
            raw_name="Olga Titova",
            raw_email="olga1@example.com",
            runner_id=guest.id,
            finish_status=FinishStatus.finished,
        )
    )
    await session.flush()
    await merge_guest_into(session, guest, real_user)
    await session.commit()

    second_event_id, x_group2, _ = await _tagged_event(session, org)
    result = await import_attendance_csv(
        session,
        second_event_id,
        "first_name;last_name;email;result\nOlga;Titova;olga2@example.com;X\n",
    )
    await session.commit()

    assert len(result.email_mismatches) == 1
    assert result.email_mismatches[0].known_email == "olga1@example.com"
    assert result.email_mismatches[0].row_email == "olga2@example.com"


@pytest.mark.asyncio
async def test_csv_missing_result_column_raises(session: AsyncSession) -> None:
    org = await make_user(session, "org-missing@example.com", UserRole.organizer)
    event, _ = await make_event_group(session, org)
    with pytest.raises(ValueError):
        await import_attendance_csv(session, event.id, "first_name;last_name\nx;y\n")


@pytest.mark.asyncio
async def test_csv_missing_name_column_raises(session: AsyncSession) -> None:
    org = await make_user(session, "org-missing2@example.com", UserRole.organizer)
    event, _ = await make_event_group(session, org)
    with pytest.raises(ValueError):
        await import_attendance_csv(session, event.id, "first_name;result\nx;X\n")


@pytest.mark.asyncio
async def test_csv_import_event_with_no_groups_raises(session: AsyncSession) -> None:
    from datetime import date

    from app.models.event import Event

    org = await make_user(session, "org-empty-event@example.com", UserRole.organizer)
    event = Event(title="No Groups", date=date(2026, 6, 1), created_by=org.id)
    session.add(event)
    await session.flush()
    with pytest.raises(ValueError):
        await import_attendance_csv(session, event.id, "first_name;last_name;result\nx;y;X\n")
