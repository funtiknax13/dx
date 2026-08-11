import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, ModerationStatus, TicketStatus, UserRole
from app.models.result import Result
from app.models.support import SupportMessage, SupportTicket
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
async def test_reject_self_reported_notifies_runner_and_removes_record(
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

    # Result and the self-reported record are both gone.
    assert (
        await session.scalar(select(Result).where(Result.attendance_record_id == rec_id)) is None
    )
    assert (
        await session.scalar(select(AttendanceRecord).where(AttendanceRecord.id == rec_id))
        is None
    )

    # The runner got a closed ticket with a staff message carrying the reason.
    ticket = await session.scalar(
        select(SupportTicket).where(SupportTicket.created_by_user_id == runner_id)
    )
    assert ticket is not None
    assert ticket.status == TicketStatus.closed
    msg = await session.scalar(
        select(SupportMessage).where(SupportMessage.ticket_id == ticket.id)
    )
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

    # The (authoritative) attendance stays; only the result is dropped.
    assert (
        await session.scalar(select(AttendanceRecord).where(AttendanceRecord.id == rec_id))
        is not None
    )
    assert await session.scalar(select(Result).where(Result.id == result_id)) is None
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
    assert await session.scalar(select(SupportTicket)) is None
