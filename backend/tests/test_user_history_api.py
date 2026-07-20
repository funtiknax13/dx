from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
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
async def test_user_history_sorted_by_event_date_not_insertion_order(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-hist-order@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-hist-order@example.com")

    # Insert the OLDER event's attendance record first (so it gets the lower
    # id), then a NEWER event's record second (higher id) — if sorting were
    # still by id, the newer one would wrongly land last instead of first.
    old_event = Event(title="Old", date=date(2020, 1, 1), created_by=org.id)
    session.add(old_event)
    await session.flush()
    old_group = Group(event_id=old_event.id, location="City", name="Old", target_distance_km=10)
    session.add(old_group)
    await session.flush()
    session.add(
        AttendanceRecord(
            group_id=old_group.id,
            raw_name="Runner",
            runner_id=runner.id,
            finish_status=FinishStatus.finished,
        )
    )
    await session.flush()

    new_event = Event(title="New", date=date(2026, 6, 1), created_by=org.id)
    session.add(new_event)
    await session.flush()
    new_group = Group(event_id=new_event.id, location="City", name="New", target_distance_km=10)
    session.add(new_group)
    await session.flush()
    session.add(
        AttendanceRecord(
            group_id=new_group.id,
            raw_name="Runner",
            runner_id=runner.id,
            finish_status=FinishStatus.finished,
        )
    )
    await session.commit()

    resp = await client.get(f"/api/v1/users/{runner.id}/history", params={"page": 1})
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [i["event_title"] for i in items] == ["New", "Old"]


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


@pytest.mark.asyncio
async def test_public_profile_locked_for_anonymous_viewer(
    session: AsyncSession, client: AsyncClient
) -> None:
    runner = await make_user(session, "runner-anon-view@example.com")
    await session.commit()

    resp = await client.get(f"/api/v1/users/{runner.id}")
    body = resp.json()
    assert body["lock_reason"] == "anonymous"
    assert body["rating"] is None
    assert body["achievements"] is None
    # Basic identity still shows — only the stats are gated.
    assert body["first_name"] == "Test"


@pytest.mark.asyncio
async def test_public_profile_locked_when_viewer_profile_incomplete(
    session: AsyncSession, client: AsyncClient
) -> None:
    runner = await make_user(session, "runner-target@example.com")
    viewer = await make_user(session, "viewer-incomplete@example.com", complete_profile=False)
    await session.commit()

    token = create_access_token(viewer.id)
    resp = await client.get(
        f"/api/v1/users/{runner.id}", headers={"Authorization": f"Bearer {token}"}
    )
    body = resp.json()
    assert body["lock_reason"] == "profile_incomplete"
    assert body["rating"] is None


@pytest.mark.asyncio
async def test_public_profile_never_locked_for_own_profile(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Viewing your own profile is never gated, even with an incomplete
    profile — the gate is only about seeing *other* runners' stats."""
    runner = await make_user(session, "runner-self@example.com", complete_profile=False)
    await session.commit()

    token = create_access_token(runner.id)
    resp = await client.get(
        f"/api/v1/users/{runner.id}", headers={"Authorization": f"Bearer {token}"}
    )
    body = resp.json()
    assert body["lock_reason"] is None
    assert body["rating"] == 0


@pytest.mark.asyncio
async def test_public_profile_unlocked_for_complete_viewer(
    session: AsyncSession, client: AsyncClient
) -> None:
    runner = await make_user(session, "runner-target2@example.com")
    viewer = await make_user(session, "viewer-complete@example.com")
    await session.commit()

    token = create_access_token(viewer.id)
    resp = await client.get(
        f"/api/v1/users/{runner.id}", headers={"Authorization": f"Bearer {token}"}
    )
    body = resp.json()
    assert body["lock_reason"] is None
    assert body["rating"] == 0
