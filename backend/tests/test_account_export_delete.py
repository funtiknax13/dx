import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, ModerationStatus, ResultSource, UserRole
from app.models.result import Result
from app.models.user import User
from tests.factories import make_event_group, make_user


def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.mark.asyncio
async def test_export_me_returns_profile_and_history(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-export@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-export@example.com")
    _, group = await make_event_group(session, org, target_km=10)
    rec = AttendanceRecord(
        group_id=group.id,
        raw_name="Runner Export",
        runner_id=runner.id,
        finish_status=FinishStatus.finished,
    )
    session.add(rec)
    await session.flush()
    session.add(
        Result(
            attendance_record_id=rec.id,
            distance_km=10.2,
            duration_seconds=3000,
            pace_seconds_per_km=294.0,
            source=ResultSource.manual,
            finish_status=FinishStatus.finished,
            status=ModerationStatus.approved,
        )
    )
    await session.commit()

    resp = await client.get("/api/v1/users/me/export", headers=_auth_headers(runner))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["profile"]["email"] == "runner-export@example.com"
    assert len(body["history"]) == 1
    entry = body["history"][0]
    assert entry["group_id"] == group.id
    assert entry["distance_km"] == 10.2
    assert entry["duration_seconds"] == 3000


@pytest.mark.asyncio
async def test_delete_me_requires_correct_password(
    session: AsyncSession, client: AsyncClient
) -> None:
    runner = await make_user(session, "runner-wrongpass@example.com")
    await session.commit()

    resp = await client.request(
        "DELETE",
        "/api/v1/users/me",
        json={"password": "not-the-password"},
        headers=_auth_headers(runner),
    )
    assert resp.status_code == 400

    still_there = await session.get(User, runner.id)
    assert still_there is not None


@pytest.mark.asyncio
async def test_delete_me_removes_account_and_anonymizes_attendance(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-delete@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-delete@example.com")
    _, group = await make_event_group(session, org)
    rec = AttendanceRecord(
        group_id=group.id,
        raw_name="Runner Delete",
        raw_email="runner-delete@example.com",
        raw_phone="+79990000000",
        runner_id=runner.id,
        finish_status=FinishStatus.finished,
    )
    session.add(rec)
    await session.commit()
    runner_id = runner.id
    rec_id = rec.id

    resp = await client.request(
        "DELETE",
        "/api/v1/users/me",
        json={"password": "password123"},
        headers=_auth_headers(runner),
    )
    assert resp.status_code == 200, resp.text

    # The delete happened via the endpoint's own session — session.get() would
    # serve this test's stale identity-map copy instead of re-querying, so use
    # a fresh select to see the real, post-delete DB state.
    session.expire_all()
    assert await session.scalar(select(User).where(User.id == runner_id)) is None

    refreshed = await session.get(AttendanceRecord, rec_id)
    assert refreshed is not None
    assert refreshed.runner_id is None
    assert refreshed.raw_email is None
    assert refreshed.raw_phone is None
    # The historical record itself (who ran, what result) is kept.
    assert refreshed.raw_name == "Runner Delete"


@pytest.mark.asyncio
async def test_delete_me_blocked_when_user_has_created_events(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-blocked@example.com", UserRole.organizer)
    await make_event_group(session, org)
    await session.commit()

    resp = await client.request(
        "DELETE",
        "/api/v1/users/me",
        json={"password": "password123"},
        headers=_auth_headers(org),
    )
    assert resp.status_code == 409

    still_there = await session.get(User, org.id)
    assert still_there is not None
