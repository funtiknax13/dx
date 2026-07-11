import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.signup import Signup
from tests.factories import make_event_group, make_user


@pytest.mark.asyncio
async def test_group_out_includes_event_date_and_signup_count(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-signups@example.com", UserRole.organizer)
    event, group = await make_event_group(session, org)
    runner = await make_user(session, "runner-signups@example.com", UserRole.runner)
    session.add(Signup(group_id=group.id, runner_id=runner.id))
    await session.commit()

    resp = await client.get(f"/api/v1/groups/{group.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["event_date"] == event.date.isoformat()
    assert body["signup_count"] == 1

    list_resp = await client.get(f"/api/v1/events/{event.id}/groups")
    assert list_resp.status_code == 200
    listed = next(g for g in list_resp.json() if g["id"] == group.id)
    assert listed["event_date"] == event.date.isoformat()
    assert listed["signup_count"] == 1


@pytest.mark.asyncio
async def test_group_signup_roster_lists_names_and_count(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-roster@example.com", UserRole.organizer)
    _event, group = await make_event_group(session, org)
    runner1 = await make_user(session, "runner-a@example.com", UserRole.runner)
    runner1.first_name, runner1.last_name = "Иван", "Бегунов"
    runner2 = await make_user(session, "runner-b@example.com", UserRole.runner)
    runner2.first_name, runner2.last_name = "Анна", "Скороходова"
    session.add_all(
        [
            Signup(group_id=group.id, runner_id=runner1.id),
            Signup(group_id=group.id, runner_id=runner2.id),
        ]
    )
    await session.commit()

    resp = await client.get(f"/api/v1/groups/{group.id}/signups")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["group_id"] == group.id
    assert body["count"] == 2
    names = {e["display_name"] for e in body["entries"]}
    assert names == {"Иван Бегунов", "Анна Скороходова"}


@pytest.mark.asyncio
async def test_group_signup_roster_empty_is_not_an_error(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-roster2@example.com", UserRole.organizer)
    _event, group = await make_event_group(session, org)
    await session.commit()

    resp = await client.get(f"/api/v1/groups/{group.id}/signups")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 0
    assert body["entries"] == []
