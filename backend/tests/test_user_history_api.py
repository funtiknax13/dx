from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, UserRole
from app.models.event import Event
from app.models.group import Group
from tests.factories import make_user


@pytest.mark.asyncio
async def test_user_history_paginates(session: AsyncSession, client: AsyncClient) -> None:
    org = await make_user(session, "org-hist@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-hist@example.com")

    for i in range(25):
        event = Event(title=f"DX #{i}", date=date(2026, 1, 1), created_by=org.id)
        session.add(event)
        await session.flush()
        group = Group(event_id=event.id, location="City", name=f"G{i}", target_distance_km=10)
        session.add(group)
        await session.flush()
        session.add(
            AttendanceRecord(
                group_id=group.id,
                raw_name="Runner",
                runner_id=runner.id,
                finish_status=FinishStatus.finished,
            )
        )
    await session.commit()

    resp = await client.get(f"/api/v1/users/{runner.id}/history", params={"page": 1})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 25
    assert len(body["items"]) == 20

    resp2 = await client.get(f"/api/v1/users/{runner.id}/history", params={"page": 2})
    assert len(resp2.json()["items"]) == 5


@pytest.mark.asyncio
async def test_user_history_404_for_missing_user(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users/999999/history")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_public_profile_no_longer_embeds_history(
    session: AsyncSession, client: AsyncClient
) -> None:
    runner = await make_user(session, "runner-nohist@example.com")
    await session.commit()

    resp = await client.get(f"/api/v1/users/{runner.id}")
    assert resp.status_code == 200, resp.text
    assert "history" not in resp.json()
