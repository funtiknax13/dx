from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.event import Event
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
