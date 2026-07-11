from datetime import UTC, date, datetime, time

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import UserRole
from app.models.group import Group
from tests.factories import make_event_group, make_user


async def _login(client: AsyncClient, user_id: int) -> None:
    token = create_access_token(user_id)
    resp = await client.get(f"/admin-tools/sso?token={token}", follow_redirects=False)
    assert resp.status_code == 302


@pytest.mark.asyncio
async def test_new_group_start_time_takes_date_from_event(
    session: AsyncSession, client: AsyncClient
) -> None:
    """The group form only collects time-of-day — the date always comes from
    the parent event, never from the submitted value."""
    org = await make_user(session, "org-groups@example.com", UserRole.organizer)
    event, _existing_group = await make_event_group(session, org)
    await session.commit()
    await _login(client, org.id)

    resp = await client.post(
        f"/admin-tools/events/{event.id}/groups/new",
        data={
            "name": "X-10 группа #2",
            "location": "Парк",
            "target_distance_km": "10",
            "start_time": "08:30",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text

    group = await session.scalar(
        select(Group).where(Group.event_id == event.id, Group.name == "X-10 группа #2")
    )
    assert group is not None
    assert group.start_time == datetime.combine(event.date, time(8, 30))


@pytest.mark.asyncio
async def test_editing_event_date_moves_group_start_times_along(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Changing the event's date must carry every group's time-of-day to the
    new date instead of leaving start_time pointing at the old date."""
    org = await make_user(session, "org-groups2@example.com", UserRole.organizer)
    event, group = await make_event_group(session, org)
    assert group.start_time == datetime(2026, 5, 1, 8, 0, tzinfo=UTC)
    await session.commit()
    await _login(client, org.id)

    resp = await client.post(
        f"/admin-tools/events/{event.id}/edit",
        data={
            "title": event.title,
            "date": "2026-05-08",
            "description": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text

    await session.refresh(group)
    await session.refresh(event)
    assert group.start_time == datetime(2026, 5, 8, 8, 0)
    assert event.date == date(2026, 5, 8)
