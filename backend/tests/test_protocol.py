import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, ModerationStatus, UserRole
from app.models.group import Group
from app.services.guest_service import create_guest, merge_guest_into
from tests.factories import make_attendance_with_result, make_event_group, make_user


@pytest.mark.asyncio
async def test_protocol_shows_current_account_name_after_guest_merge(
    session: AsyncSession, client: AsyncClient
) -> None:
    """A guest merged into a real account must show the real account's current
    name in the protocol — not the raw_name frozen from the CSV row that
    originally created the guest. Otherwise the same person reads as two
    different people (see conversation: "Марина Неопознанная" vs
    "Марина Настоящая")."""
    org = await make_user(session, "org@example.com", UserRole.organizer)
    real_user = await make_user(session, "marina@example.com")
    real_user.first_name = "Марина"
    real_user.last_name = "Настоящая"
    _, group = await make_event_group(session, org)

    guest = await create_guest(session, "Марина Неопознанная")
    rec = AttendanceRecord(
        group_id=group.id,
        raw_name="Марина Неопознанная",
        runner_id=guest.id,
        finish_status=FinishStatus.finished,
    )
    session.add(rec)
    await session.flush()

    await merge_guest_into(session, guest, real_user)
    await session.commit()

    resp = await client.get(f"/api/v1/groups/{group.id}/protocol")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    entries = body["finishers"] + body["pending"] + body["dnf"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["display_name"] == "Марина Настоящая"
    assert entry["runner_id"] == real_user.id


@pytest.mark.asyncio
async def test_protocol_merges_groups_sharing_distance_code(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Two pace-subgroups tagged with the same distance_code (e.g. "X-33 группа
    #1" and "#2") should share one protocol — a third, differently-tagged group
    in the same event must stay out of it."""
    org = await make_user(session, "org-merge@example.com", UserRole.organizer)
    runner1 = await make_user(session, "runner1-merge@example.com")
    runner2 = await make_user(session, "runner2-merge@example.com")
    runner3 = await make_user(session, "runner3-merge@example.com")
    event, group1 = await make_event_group(session, org, target_km=33)
    group1.name = "X-33 группа #1"
    group1.distance_code = "X-33"
    group2 = Group(
        event_id=event.id,
        location="City",
        name="X-33 группа #2",
        distance_code="X-33",
        target_distance_km=33,
    )
    other_group = Group(
        event_id=event.id,
        location="City",
        name="P-10 группа #1",
        distance_code="P-10",
        target_distance_km=10,
    )
    session.add_all([group2, other_group])
    await session.flush()

    session.add(
        AttendanceRecord(
            group_id=group1.id,
            raw_name="R1",
            runner_id=runner1.id,
            finish_status=FinishStatus.finished,
        )
    )
    session.add(
        AttendanceRecord(
            group_id=group2.id,
            raw_name="R2",
            runner_id=runner2.id,
            finish_status=FinishStatus.finished,
        )
    )
    session.add(
        AttendanceRecord(
            group_id=other_group.id,
            raw_name="R3",
            runner_id=runner3.id,
            finish_status=FinishStatus.finished,
        )
    )
    await session.commit()

    resp = await client.get(f"/api/v1/groups/{group1.id}/protocol")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert sorted(body["group_ids"]) == sorted([group1.id, group2.id])
    entries = body["finishers"] + body["pending"] + body["dnf"]
    assert {e["runner_id"] for e in entries} == {runner1.id, runner2.id}

    # A group without a distance_code (or a different one) is unaffected.
    resp2 = await client.get(f"/api/v1/groups/{other_group.id}/protocol")
    body2 = resp2.json()
    assert body2["group_ids"] == [other_group.id]


@pytest.mark.asyncio
async def test_protocol_entry_includes_latest_achievement(
    session: AsyncSession, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import achievement_service

    monkeypatch.setattr(achievement_service, "ACHIEVEMENT_MILESTONES", [1, 2])

    org = await make_user(session, "org-badge@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-badge@example.com")
    _, group = await make_event_group(session, org)
    session.add(
        AttendanceRecord(
            group_id=group.id,
            raw_name="Runner",
            runner_id=runner.id,
            finish_status=FinishStatus.finished,
        )
    )
    await session.commit()

    resp = await client.get(f"/api/v1/groups/{group.id}/protocol")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    entries = body["finishers"] + body["pending"] + body["dnf"]
    assert len(entries) == 1
    assert entries[0]["latest_achievement"] == 1


@pytest.mark.asyncio
async def test_protocol_entry_includes_runners_avatar(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-avatar@example.com", UserRole.organizer)
    runner = await make_user(session, "avatar-runner@example.com")
    runner.avatar = "/media/avatars/test.jpg"
    _, group = await make_event_group(session, org)
    session.add(
        AttendanceRecord(
            group_id=group.id,
            raw_name="Avatar Runner",
            runner_id=runner.id,
            finish_status=FinishStatus.finished,
        )
    )
    await session.commit()

    resp = await client.get(f"/api/v1/groups/{group.id}/protocol")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    entries = body["finishers"] + body["pending"] + body["dnf"]
    assert len(entries) == 1
    assert entries[0]["avatar"] == "/media/avatars/test.jpg"


@pytest.mark.asyncio
async def test_protocol_finishers_with_equal_time_break_tie_by_name(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-nametie@example.com", UserRole.organizer)
    _, group = await make_event_group(session, org)
    runner_b = await make_user(session, "runner-b-nametie@example.com")
    runner_b.first_name, runner_b.last_name = "Иван", "Борисов"
    runner_a = await make_user(session, "runner-a-nametie@example.com")
    runner_a.first_name, runner_a.last_name = "Пётр", "Антонов"

    # Same fixed duration_seconds=3000 for both (see factories.make_attendance_with_result)
    # -> only the name tiebreak can decide the order.
    await make_attendance_with_result(
        session, group, runner_b,
        finish_status=FinishStatus.finished, moderation=ModerationStatus.approved,
    )
    await make_attendance_with_result(
        session, group, runner_a,
        finish_status=FinishStatus.finished, moderation=ModerationStatus.approved,
    )
    await session.commit()

    resp = await client.get(f"/api/v1/groups/{group.id}/protocol")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [e["runner_id"] for e in body["finishers"]] == [runner_a.id, runner_b.id]
    assert [e["rank"] for e in body["finishers"]] == [1, 2]


@pytest.mark.asyncio
async def test_protocol_pending_entries_sorted_by_name(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-pendingsort@example.com", UserRole.organizer)
    _, group = await make_event_group(session, org)
    runner_z = await make_user(session, "runner-z-pending@example.com")
    runner_z.first_name, runner_z.last_name = "Анна", "Яковлева"
    runner_a = await make_user(session, "runner-a-pending@example.com")
    runner_a.first_name, runner_a.last_name = "Борис", "Волков"

    for runner in (runner_z, runner_a):
        session.add(
            AttendanceRecord(
                group_id=group.id,
                raw_name=f"{runner.first_name} {runner.last_name}",
                runner_id=runner.id,
                finish_status=FinishStatus.finished,
            )
        )
    await session.commit()

    resp = await client.get(f"/api/v1/groups/{group.id}/protocol")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [e["runner_id"] for e in body["pending"]] == [runner_a.id, runner_z.id]


@pytest.mark.asyncio
async def test_protocol_dnf_entries_sorted_by_name(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-dnfsort@example.com", UserRole.organizer)
    _, group = await make_event_group(session, org)
    runner_z = await make_user(session, "runner-z-dnf@example.com")
    runner_z.first_name, runner_z.last_name = "Анна", "Яковлева"
    runner_a = await make_user(session, "runner-a-dnf@example.com")
    runner_a.first_name, runner_a.last_name = "Борис", "Волков"

    for runner in (runner_z, runner_a):
        session.add(
            AttendanceRecord(
                group_id=group.id,
                raw_name=f"{runner.first_name} {runner.last_name}",
                runner_id=runner.id,
                finish_status=FinishStatus.dnf,
            )
        )
    await session.commit()

    resp = await client.get(f"/api/v1/groups/{group.id}/protocol")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [e["runner_id"] for e in body["dnf"]] == [runner_a.id, runner_z.id]
