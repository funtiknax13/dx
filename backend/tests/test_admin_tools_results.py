import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.attendance import AttendanceRecord
from app.models.enums import (
    FinishStatus,
    ModerationStatus,
    StaffPermission,
    TicketStatus,
    UserRole,
)
from app.models.result import Result
from app.models.support import SupportMessage, SupportTicket
from app.services.permissions_service import set_permissions
from tests.factories import make_attendance_with_result, make_event_group, make_user


async def _login(client: AsyncClient, user_id: int) -> None:
    token = create_access_token(user_id)
    resp = await client.get(f"/admin-tools/sso?token={token}", follow_redirects=False)
    assert resp.status_code == 302


async def _result_id(session: AsyncSession, attendance_id: int) -> int:
    rid = await session.scalar(
        select(Result.id).where(Result.attendance_record_id == attendance_id)
    )
    assert rid is not None
    return rid


@pytest.mark.asyncio
async def test_reject_marks_rejected_and_notifies_runner(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-reject1@example.com", UserRole.admin)
    org = await make_user(session, "org-reject1@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-reject1@example.com")
    _, group = await make_event_group(session, org)
    rec = await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.pending,
        self_reported=True,
    )
    # Capture ids as plain ints — the ORM objects expire on the commit below.
    rec_id, runner_id = rec.id, runner.id
    result_id = await _result_id(session, rec_id)
    admin_id = admin.id
    await session.commit()
    await _login(client, admin_id)

    resp = await client.post(
        f"/admin-tools/results/{result_id}/reject",
        data={"reason": "На скриншоте не совпадает дата старта."},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    session.expire_all()

    # The result is kept but marked rejected (not deleted); the record stays.
    result = await session.scalar(select(Result).where(Result.id == result_id))
    assert result is not None
    assert result.status == ModerationStatus.rejected
    assert await session.get(AttendanceRecord, rec_id) is not None

    # The runner got a closed ticket with a staff message carrying the reason.
    ticket = await session.scalar(
        select(SupportTicket).where(SupportTicket.created_by_user_id == runner_id)
    )
    assert ticket is not None
    assert ticket.status == TicketStatus.closed
    msg = await session.scalar(select(SupportMessage).where(SupportMessage.ticket_id == ticket.id))
    assert msg is not None
    assert msg.is_staff is True
    assert "не совпадает дата старта" in msg.body
    assert "не принят" in msg.body


@pytest.mark.asyncio
async def test_reject_csv_record_keeps_attendance(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-reject2@example.com", UserRole.admin)
    org = await make_user(session, "org-reject2@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-reject2@example.com")
    _, group = await make_event_group(session, org)
    rec = await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.pending,
        self_reported=False,
    )
    rec_id, runner_id = rec.id, runner.id
    result_id = await _result_id(session, rec_id)
    admin_id = admin.id
    await session.commit()
    await _login(client, admin_id)

    resp = await client.post(
        f"/admin-tools/results/{result_id}/reject",
        data={"reason": "Скриншот нечитаемый."},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    session.expire_all()

    # The attendance stays and the result is kept, marked rejected.
    assert await session.get(AttendanceRecord, rec_id) is not None
    result = await session.scalar(select(Result).where(Result.id == result_id))
    assert result is not None
    assert result.status == ModerationStatus.rejected
    # Runner still notified.
    assert (
        await session.scalar(
            select(SupportTicket).where(SupportTicket.created_by_user_id == runner_id)
        )
        is not None
    )


@pytest.mark.asyncio
async def test_reject_unmatched_record_creates_no_ticket(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-reject3@example.com", UserRole.admin)
    org = await make_user(session, "org-reject3@example.com", UserRole.organizer)
    _, group = await make_event_group(session, org)
    rec = await make_attendance_with_result(
        session,
        group,
        None,  # no account behind this record
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.pending,
    )
    result_id = await _result_id(session, rec.id)
    admin_id = admin.id
    await session.commit()
    await _login(client, admin_id)

    resp = await client.post(
        f"/admin-tools/results/{result_id}/reject",
        data={"reason": "Нет трека."},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    session.expire_all()
    assert await session.scalar(select(SupportTicket)) is None
    result = await session.scalar(select(Result).where(Result.id == result_id))
    assert result is not None and result.status == ModerationStatus.rejected


@pytest.mark.asyncio
async def test_reject_twice_sends_only_one_ticket(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Regression guard: a double-click/double-submit of the reject form (it
    has no client-side guard of its own) must not email the runner twice."""
    admin = await make_user(session, "admin-reject4@example.com", UserRole.admin)
    org = await make_user(session, "org-reject4@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-reject4@example.com")
    _, group = await make_event_group(session, org)
    rec = await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.pending,
        self_reported=True,
    )
    runner_id = runner.id
    result_id = await _result_id(session, rec.id)
    admin_id = admin.id
    await session.commit()
    await _login(client, admin_id)

    first = await client.post(
        f"/admin-tools/results/{result_id}/reject",
        data={"reason": "Первая причина."},
        follow_redirects=False,
    )
    second = await client.post(
        f"/admin-tools/results/{result_id}/reject",
        data={"reason": "Вторая причина."},
        follow_redirects=False,
    )
    assert first.status_code == 303
    assert second.status_code == 303
    session.expire_all()

    tickets = list(
        await session.scalars(
            select(SupportTicket).where(SupportTicket.created_by_user_id == runner_id)
        )
    )
    assert len(tickets) == 1
    messages = list(
        await session.scalars(
            select(SupportMessage).where(SupportMessage.ticket_id == tickets[0].id)
        )
    )
    assert len(messages) == 1
    assert "Первая причина" in messages[0].body


@pytest.mark.asyncio
async def test_approve_as_dnf_flips_record_and_notifies(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-dnf1@example.com", UserRole.admin)
    org = await make_user(session, "org-dnf1@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-dnf1@example.com")
    _, group = await make_event_group(session, org, target_km=23.0)
    rec = await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.pending,
        self_reported=True,
    )
    rec_id, runner_id = rec.id, runner.id
    result_id = await _result_id(session, rec_id)
    admin_id = admin.id
    await session.commit()
    await _login(client, admin_id)

    resp = await client.post(
        f"/admin-tools/results/{result_id}/approve-dnf", follow_redirects=False
    )
    assert resp.status_code == 303
    session.expire_all()

    # Both the record and the result flip to dnf together, and the result is
    # settled (approved), not left pending or marked rejected.
    record = await session.get(AttendanceRecord, rec_id)
    assert record is not None
    assert record.finish_status == FinishStatus.dnf
    result = await session.scalar(select(Result).where(Result.id == result_id))
    assert result is not None
    assert result.finish_status == FinishStatus.dnf
    assert result.status == ModerationStatus.approved

    ticket = await session.scalar(
        select(SupportTicket).where(SupportTicket.created_by_user_id == runner_id)
    )
    assert ticket is not None
    assert ticket.status == TicketStatus.closed
    msg = await session.scalar(select(SupportMessage).where(SupportMessage.ticket_id == ticket.id))
    assert msg is not None
    assert "DNF" in msg.body


@pytest.mark.asyncio
async def test_approve_as_dnf_twice_sends_only_one_ticket(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-dnf2@example.com", UserRole.admin)
    org = await make_user(session, "org-dnf2@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-dnf2@example.com")
    _, group = await make_event_group(session, org)
    rec = await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.pending,
        self_reported=True,
    )
    runner_id = runner.id
    result_id = await _result_id(session, rec.id)
    admin_id = admin.id
    await session.commit()
    await _login(client, admin_id)

    first = await client.post(
        f"/admin-tools/results/{result_id}/approve-dnf", follow_redirects=False
    )
    second = await client.post(
        f"/admin-tools/results/{result_id}/approve-dnf", follow_redirects=False
    )
    assert first.status_code == 303
    assert second.status_code == 303
    session.expire_all()

    tickets = list(
        await session.scalars(
            select(SupportTicket).where(SupportTicket.created_by_user_id == runner_id)
        )
    )
    assert len(tickets) == 1


# --- /results/fix (correcting an already-settled record) --------------------


@pytest.mark.asyncio
async def test_results_fix_search_finds_record_by_name(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-fix1@example.com", UserRole.admin)
    org = await make_user(session, "org-fix1@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-fix1@example.com")
    runner.first_name, runner.last_name = "Иннокентий", "Фиксов"
    _, group = await make_event_group(session, org)
    await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.approved,
    )
    admin_id = admin.id
    await session.commit()
    await _login(client, admin_id)

    resp = await client.get("/admin-tools/results/fix?q=Фиксов")
    assert resp.status_code == 200
    assert "Иннокентий Фиксов" in resp.text
    assert "Поставить DNF" in resp.text
    # The action form must round-trip the search term as a hidden field —
    # otherwise the search resets to empty after the POST (see
    # test_results_fix_set_dnf_preserves_the_search_query below).
    assert '<input type="hidden" name="q" value="Фиксов">' in resp.text


@pytest.mark.asyncio
async def test_results_fix_set_dnf_preserves_the_search_query(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Regression guard: the redirect after set-dnf/unset-dnf must land back
    on the same search, not reset to an empty, record-less list."""
    admin = await make_user(session, "admin-fixq@example.com", UserRole.admin)
    org = await make_user(session, "org-fixq@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-fixq@example.com")
    runner.first_name, runner.last_name = "Поиск", "Выживший"
    _, group = await make_event_group(session, org)
    rec = await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.approved,
    )
    rec_id = rec.id
    admin_id = admin.id
    await session.commit()
    await _login(client, admin_id)

    resp = await client.post(
        f"/admin-tools/results/fix/{rec_id}/set-dnf",
        data={"q": "Выживший"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "q=" in resp.headers["location"]

    followed = await client.get(resp.headers["location"])
    assert "Поиск Выживший" in followed.text


@pytest.mark.asyncio
async def test_results_fix_set_dnf_syncs_record_and_result_and_notifies(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-fix2@example.com", UserRole.admin)
    org = await make_user(session, "org-fix2@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-fix2@example.com")
    _, group = await make_event_group(session, org)
    rec = await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.approved,
    )
    rec_id, runner_id = rec.id, runner.id
    admin_id = admin.id
    await session.commit()
    await _login(client, admin_id)

    resp = await client.post(f"/admin-tools/results/fix/{rec_id}/set-dnf", follow_redirects=False)
    assert resp.status_code == 303
    session.expire_all()

    record = await session.get(AttendanceRecord, rec_id)
    assert record is not None
    assert record.finish_status == FinishStatus.dnf
    result = await session.scalar(select(Result).where(Result.attendance_record_id == rec_id))
    assert result is not None
    assert result.finish_status == FinishStatus.dnf
    # Moderation status is left exactly as it was — this is a finish_status
    # correction, not a re-review of the result's data.
    assert result.status == ModerationStatus.approved

    ticket = await session.scalar(
        select(SupportTicket).where(SupportTicket.created_by_user_id == runner_id)
    )
    assert ticket is not None
    msg = await session.scalar(select(SupportMessage).where(SupportMessage.ticket_id == ticket.id))
    assert msg is not None
    assert "DNF" in msg.body


@pytest.mark.asyncio
async def test_results_fix_set_dnf_works_without_a_result_row(
    session: AsyncSession, client: AsyncClient
) -> None:
    """A CSV-only participation (finish_status set at import, no uploaded
    Result at all) must still be fixable — there's nothing to sync on the
    Result side, just the record itself."""
    admin = await make_user(session, "admin-fix3@example.com", UserRole.admin)
    org = await make_user(session, "org-fix3@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-fix3@example.com")
    _, group = await make_event_group(session, org)
    rec = AttendanceRecord(
        group_id=group.id,
        raw_name=f"{runner.first_name} {runner.last_name}",
        runner_id=runner.id,
        finish_status=FinishStatus.finished,
    )
    session.add(rec)
    await session.flush()
    rec_id = rec.id
    admin_id = admin.id
    await session.commit()
    await _login(client, admin_id)

    resp = await client.post(f"/admin-tools/results/fix/{rec_id}/set-dnf", follow_redirects=False)
    assert resp.status_code == 303
    session.expire_all()
    record = await session.get(AttendanceRecord, rec_id)
    assert record is not None
    assert record.finish_status == FinishStatus.dnf


@pytest.mark.asyncio
async def test_results_fix_unset_dnf_reverts_to_finished(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-fix4@example.com", UserRole.admin)
    org = await make_user(session, "org-fix4@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-fix4@example.com")
    _, group = await make_event_group(session, org)
    rec = await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.dnf,
        moderation=ModerationStatus.approved,
    )
    rec_id = rec.id
    admin_id = admin.id
    await session.commit()
    await _login(client, admin_id)

    resp = await client.post(f"/admin-tools/results/fix/{rec_id}/unset-dnf", follow_redirects=False)
    assert resp.status_code == 303
    session.expire_all()

    record = await session.get(AttendanceRecord, rec_id)
    assert record is not None
    assert record.finish_status == FinishStatus.finished
    result = await session.scalar(select(Result).where(Result.attendance_record_id == rec_id))
    assert result is not None
    assert result.finish_status == FinishStatus.finished


@pytest.mark.asyncio
async def test_results_fix_set_dnf_twice_sends_only_one_ticket(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-fix5@example.com", UserRole.admin)
    org = await make_user(session, "org-fix5@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-fix5@example.com")
    _, group = await make_event_group(session, org)
    rec = await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.approved,
    )
    rec_id, runner_id = rec.id, runner.id
    admin_id = admin.id
    await session.commit()
    await _login(client, admin_id)

    await client.post(f"/admin-tools/results/fix/{rec_id}/set-dnf", follow_redirects=False)
    await client.post(f"/admin-tools/results/fix/{rec_id}/set-dnf", follow_redirects=False)
    session.expire_all()

    tickets = list(
        await session.scalars(
            select(SupportTicket).where(SupportTicket.created_by_user_id == runner_id)
        )
    )
    assert len(tickets) == 1


@pytest.mark.asyncio
async def test_results_fix_organizer_cannot_fix_another_organizers_event(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-fix6@example.com", UserRole.admin)
    owner = await make_user(session, "owner-fix6@example.com", UserRole.organizer)
    other = await make_user(session, "other-fix6@example.com", UserRole.organizer)
    await set_permissions(session, other, {StaffPermission.results_review}, granted_by=admin)
    runner = await make_user(session, "runner-fix6@example.com")
    _, group = await make_event_group(session, owner)
    rec = await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.approved,
    )
    rec_id = rec.id
    other_id = other.id
    await session.commit()
    await _login(client, other_id)

    resp = await client.post(f"/admin-tools/results/fix/{rec_id}/set-dnf", follow_redirects=False)
    assert resp.status_code == 303
    session.expire_all()
    record = await session.get(AttendanceRecord, rec_id)
    assert record is not None
    assert record.finish_status == FinishStatus.finished
