import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, UserRole
from app.services.guest_service import create_guest, merge_guest_into
from tests.factories import make_event_group, make_user


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
