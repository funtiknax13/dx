from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import UserRole
from app.models.group import Group
from app.models.signup import Signup
from tests.factories import make_event_group, make_user


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


@pytest.mark.asyncio
async def test_signing_up_for_another_group_switches_instead_of_duplicating(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-switch@example.com", UserRole.organizer)
    event, group_a = await make_event_group(session, org)
    group_b = Group(
        event_id=event.id, location="Другое место", name="Group B", target_distance_km=15
    )
    session.add(group_b)
    runner = await make_user(session, "switcher@example.com", UserRole.runner)
    await session.commit()

    r1 = await client.post(f"/api/v1/groups/{group_a.id}/signups", headers=_auth(runner.id))
    assert r1.status_code == 201, r1.text
    first_signup_id = r1.json()["id"]

    r2 = await client.post(f"/api/v1/groups/{group_b.id}/signups", headers=_auth(runner.id))
    assert r2.status_code == 201, r2.text
    assert r2.json()["id"] == first_signup_id  # same row, moved — not a new one
    assert r2.json()["group_id"] == group_b.id

    all_signups = list(
        await session.scalars(select(Signup).where(Signup.runner_id == runner.id))
    )
    assert len(all_signups) == 1
    assert all_signups[0].group_id == group_b.id


@pytest.mark.asyncio
async def test_group_signup_state_reports_other_group_in_same_event(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-other@example.com", UserRole.organizer)
    event, group_a = await make_event_group(session, org)
    group_b = Group(
        event_id=event.id, location="Другое место", name="Group B", target_distance_km=15
    )
    session.add(group_b)
    runner = await make_user(session, "other-group@example.com", UserRole.runner)
    await session.commit()

    await client.post(f"/api/v1/groups/{group_a.id}/signups", headers=_auth(runner.id))

    resp = await client.get(f"/api/v1/groups/{group_b.id}/signups/me", headers=_auth(runner.id))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["signed_up"] is False
    assert body["other_group"] == {"group_id": group_a.id, "group_name": group_a.name}


@pytest.mark.asyncio
async def test_event_signup_state_reflects_current_group(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-event-state@example.com", UserRole.organizer)
    event, group = await make_event_group(session, org)
    runner = await make_user(session, "event-state@example.com", UserRole.runner)
    await session.commit()

    before = await client.get(f"/api/v1/events/{event.id}/signups/me", headers=_auth(runner.id))
    assert before.json() == {"signed_up": False, "group_id": None, "group_name": None}

    await client.post(f"/api/v1/groups/{group.id}/signups", headers=_auth(runner.id))

    after = await client.get(f"/api/v1/events/{event.id}/signups/me", headers=_auth(runner.id))
    assert after.json() == {
        "signed_up": True,
        "group_id": group.id,
        "group_name": group.name,
    }


@pytest.mark.asyncio
async def test_my_signups_only_lists_upcoming_events(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-upcoming@example.com", UserRole.organizer)
    future_event, future_group = await make_event_group(session, org)
    future_event.date = date.today() + timedelta(days=7)

    past_event, past_group = await make_event_group(session, org)
    past_event.date = date.today() - timedelta(days=7)

    runner = await make_user(session, "upcoming@example.com", UserRole.runner)
    session.add_all(
        [
            Signup(runner_id=runner.id, group_id=future_group.id, event_id=future_event.id),
            Signup(runner_id=runner.id, group_id=past_group.id, event_id=past_event.id),
        ]
    )
    await session.commit()

    resp = await client.get("/api/v1/users/me/signups", headers=_auth(runner.id))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["event_id"] == future_event.id
    assert body[0]["group_id"] == future_group.id


@pytest.mark.asyncio
async def test_signups_for_different_events_are_both_allowed(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-multi@example.com", UserRole.organizer)
    event1, group1 = await make_event_group(session, org)
    event2, group2 = await make_event_group(session, org)
    runner = await make_user(session, "multi-event@example.com", UserRole.runner)
    await session.commit()

    r1 = await client.post(f"/api/v1/groups/{group1.id}/signups", headers=_auth(runner.id))
    r2 = await client.post(f"/api/v1/groups/{group2.id}/signups", headers=_auth(runner.id))
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]

    all_signups = list(
        await session.scalars(select(Signup).where(Signup.runner_id == runner.id))
    )
    assert len(all_signups) == 2
