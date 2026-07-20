from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezone import EVENT_TZ
from app.models.enums import UserRole
from app.models.event import Event
from app.models.group import Group
from tests.factories import make_user


@pytest.mark.asyncio
async def test_events_list_paginates(session: AsyncSession, client: AsyncClient) -> None:
    org = await make_user(session, "org-evpage@example.com", UserRole.organizer)
    today = date.today()
    for i in range(25):
        session.add(Event(title=f"DX #{i}", date=today - timedelta(days=i), created_by=org.id))
    await session.commit()

    resp = await client.get("/api/v1/events", params={"page": 1, "page_size": 20})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 25
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert len(body["items"]) == 20

    resp2 = await client.get("/api/v1/events", params={"page": 2, "page_size": 20})
    body2 = resp2.json()
    assert len(body2["items"]) == 5


@pytest.mark.asyncio
async def test_events_upcoming_filter_and_order(session: AsyncSession, client: AsyncClient) -> None:
    org = await make_user(session, "org-evfilter@example.com", UserRole.organizer)
    today = date.today()
    past = Event(title="Past", date=today - timedelta(days=7), created_by=org.id)
    soon = Event(title="Soon", date=today + timedelta(days=7), created_by=org.id)
    later = Event(title="Later", date=today + timedelta(days=14), created_by=org.id)
    session.add_all([past, soon, later])
    await session.commit()

    resp = await client.get("/api/v1/events", params={"upcoming": "true"})
    body = resp.json()
    titles = [e["title"] for e in body["items"]]
    assert titles == ["Soon", "Later"]  # ascending, soonest first, past excluded

    resp2 = await client.get("/api/v1/events", params={"upcoming": "false"})
    body2 = resp2.json()
    assert [e["title"] for e in body2["items"]] == ["Past"]


@pytest.mark.asyncio
async def test_events_today_moves_to_past_once_all_groups_started(
    session: AsyncSession, client: AsyncClient
) -> None:
    """A today-dated event whose only group already started (by wall-clock
    time, not just calendar date) should show up as "past", not linger in
    "upcoming" until midnight — this is the actual bug report: a
    still-showing-as-upcoming event that had clearly already happened."""
    org = await make_user(session, "org-evstart1@example.com", UserRole.organizer)
    now = datetime.now(EVENT_TZ)
    today = now.date()
    event = Event(title="Today Started", date=today, created_by=org.id)
    session.add(event)
    await session.flush()
    session.add(
        Group(
            event_id=event.id,
            location="City",
            name="A",
            target_distance_km=10,
            start_time=now - timedelta(hours=2),
        )
    )
    await session.commit()

    resp = await client.get("/api/v1/events", params={"upcoming": "true"})
    assert "Today Started" not in [e["title"] for e in resp.json()["items"]]

    resp2 = await client.get("/api/v1/events", params={"upcoming": "false"})
    assert "Today Started" in [e["title"] for e in resp2.json()["items"]]


@pytest.mark.asyncio
async def test_events_today_stays_upcoming_before_group_start_time(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-evstart2@example.com", UserRole.organizer)
    now = datetime.now(EVENT_TZ)
    today = now.date()
    event = Event(title="Today Not Yet", date=today, created_by=org.id)
    session.add(event)
    await session.flush()
    session.add(
        Group(
            event_id=event.id,
            location="City",
            name="A",
            target_distance_km=10,
            start_time=now + timedelta(hours=2),
        )
    )
    await session.commit()

    resp = await client.get("/api/v1/events", params={"upcoming": "true"})
    assert "Today Not Yet" in [e["title"] for e in resp.json()["items"]]
    resp2 = await client.get("/api/v1/events", params={"upcoming": "false"})
    assert "Today Not Yet" not in [e["title"] for e in resp2.json()["items"]]


@pytest.mark.asyncio
async def test_events_today_stays_upcoming_if_any_group_missing_start_time(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Even if one group already started, an event with *any* group missing a
    start_time can't be judged "fully started" — stays upcoming until the
    calendar date rolls over, same as before this feature existed."""
    org = await make_user(session, "org-evstart3@example.com", UserRole.organizer)
    now = datetime.now(EVENT_TZ)
    today = now.date()
    event = Event(title="Today Partial", date=today, created_by=org.id)
    session.add(event)
    await session.flush()
    session.add_all(
        [
            Group(
                event_id=event.id,
                location="City",
                name="A",
                target_distance_km=10,
                start_time=now - timedelta(hours=2),
            ),
            Group(event_id=event.id, location="City", name="B", target_distance_km=5),
        ]
    )
    await session.commit()

    resp = await client.get("/api/v1/events", params={"upcoming": "true"})
    assert "Today Partial" in [e["title"] for e in resp.json()["items"]]


@pytest.mark.asyncio
async def test_events_today_with_no_groups_stays_upcoming(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-evstart4@example.com", UserRole.organizer)
    today = datetime.now(EVENT_TZ).date()
    session.add(Event(title="Today No Groups", date=today, created_by=org.id))
    await session.commit()

    resp = await client.get("/api/v1/events", params={"upcoming": "true"})
    assert "Today No Groups" in [e["title"] for e in resp.json()["items"]]
