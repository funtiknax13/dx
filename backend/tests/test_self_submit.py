from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, ModerationStatus, UserRole
from app.models.signup import Signup
from tests.factories import make_event_group, make_user

_IMG = {"image": ("shot.png", b"fake-image-bytes", "image/png")}


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


async def _matched_record(session: AsyncSession, org_email: str, runner_email: str) -> tuple:
    org = await make_user(session, org_email, UserRole.organizer)
    event, group = await make_event_group(session, org)  # past date (2026-05-01)
    runner = await make_user(session, runner_email)
    rec = AttendanceRecord(
        group_id=group.id, raw_name="R", runner_id=runner.id, finish_status=FinishStatus.finished
    )
    session.add(rec)
    await session.commit()
    return runner, group, rec


@pytest.mark.asyncio
async def test_runner_cannot_upload_gpx_file(session: AsyncSession, client: AsyncClient) -> None:
    runner, _group, rec = await _matched_record(session, "org-gpx@e.com", "run-gpx@e.com")
    r = await client.post(
        f"/api/v1/attendance/{rec.id}/result",
        headers=_auth(runner.id),
        files={"file": ("run.gpx", b"<gpx/>", "application/gpx+xml")},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_runner_cannot_import_url(session: AsyncSession, client: AsyncClient) -> None:
    runner, _group, rec = await _matched_record(session, "org-url@e.com", "run-url@e.com")
    r = await client.post(
        f"/api/v1/attendance/{rec.id}/result/import-url",
        headers=_auth(runner.id),
        json={"url": "https://example.com/run.gpx"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_manual_requires_screenshot(session: AsyncSession, client: AsyncClient) -> None:
    runner, _group, rec = await _matched_record(session, "org-scr@e.com", "run-scr@e.com")
    without = await client.post(
        f"/api/v1/attendance/{rec.id}/result",
        headers=_auth(runner.id),
        data={"distance_km": "10", "duration_seconds": "3000"},
    )
    assert without.status_code == 422

    with_shot = await client.post(
        f"/api/v1/attendance/{rec.id}/result",
        headers=_auth(runner.id),
        data={"distance_km": "10", "duration_seconds": "3000"},
        files=_IMG,
    )
    assert with_shot.status_code == 201, with_shot.text


@pytest.mark.asyncio
async def test_self_submit_before_protocol_creates_self_reported(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-self@e.com", UserRole.organizer)
    event, group = await make_event_group(session, org)  # past
    group.distance_code = "X-10"
    runner = await make_user(session, "run-self@e.com")
    session.add(Signup(runner_id=runner.id, group_id=group.id, event_id=event.id))
    await session.commit()

    r = await client.post(
        f"/api/v1/groups/{group.id}/result",
        headers=_auth(runner.id),
        data={"distance_km": "10", "duration_seconds": "3000"},
        files=_IMG,
    )
    assert r.status_code == 201, r.text

    rec = await session.scalar(
        select(AttendanceRecord).where(AttendanceRecord.runner_id == runner.id)
    )
    assert rec is not None
    assert rec.self_reported is True
    assert rec.finish_status == FinishStatus.finished
    await session.refresh(rec, attribute_names=["result"])
    assert rec.result is not None and rec.result.status == ModerationStatus.pending


@pytest.mark.asyncio
async def test_self_submit_requires_signup(session: AsyncSession, client: AsyncClient) -> None:
    org = await make_user(session, "org-nosig@e.com", UserRole.organizer)
    _event, group = await make_event_group(session, org)
    runner = await make_user(session, "run-nosig@e.com")  # not signed up
    await session.commit()
    r = await client.post(
        f"/api/v1/groups/{group.id}/result",
        headers=_auth(runner.id),
        data={"distance_km": "10", "duration_seconds": "3000"},
        files=_IMG,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_self_submit_future_event_blocked(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-fut@e.com", UserRole.organizer)
    event, group = await make_event_group(session, org)
    event.date = date(2099, 1, 1)
    group.start_time = datetime(2099, 1, 1, 8, 0, tzinfo=UTC)
    runner = await make_user(session, "run-fut@e.com")
    session.add(Signup(runner_id=runner.id, group_id=group.id, event_id=event.id))
    await session.commit()

    r = await client.post(
        f"/api/v1/groups/{group.id}/result",
        headers=_auth(runner.id),
        data={"distance_km": "10", "duration_seconds": "3000"},
        files=_IMG,
    )
    assert r.status_code == 409
