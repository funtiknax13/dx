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

_IMG = {"images": ("shot.png", b"fake-image-bytes", "image/png")}


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
async def test_manual_result_stores_optional_comment(
    session: AsyncSession, client: AsyncClient
) -> None:
    runner, _group, rec = await _matched_record(session, "org-cmt@e.com", "run-cmt@e.com")
    r = await client.post(
        f"/api/v1/attendance/{rec.id}/result",
        headers=_auth(runner.id),
        data={
            "distance_km": "10",
            "duration_seconds": "3000",
            "comment": "  Отвалился GPS на 5-м км, добежал по памяти  ",
        },
        files=_IMG,
    )
    assert r.status_code == 201, r.text
    assert r.json()["comment"] == "Отвалился GPS на 5-м км, добежал по памяти"

    # A blank comment on a different record is normalised to null.
    _, _g2, rec2 = await _matched_record(session, "org-cmt2@e.com", "run-cmt2@e.com")
    runner2 = rec2.runner_id
    assert runner2 is not None
    r2 = await client.post(
        f"/api/v1/attendance/{rec2.id}/result",
        headers=_auth(runner2),
        data={"distance_km": "10", "duration_seconds": "3000", "comment": "   "},
        files=_IMG,
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["comment"] is None


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


@pytest.mark.asyncio
async def test_self_submit_accepts_multiple_screenshots(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Several screenshots are allowed when one screen can't show the date and
    the track at once — all are stored on the result."""
    org = await make_user(session, "org-multi@e.com", UserRole.organizer)
    event, group = await make_event_group(session, org)  # past
    runner = await make_user(session, "run-multi@e.com")
    session.add(Signup(runner_id=runner.id, group_id=group.id, event_id=event.id))
    await session.commit()

    r = await client.post(
        f"/api/v1/groups/{group.id}/result",
        headers=_auth(runner.id),
        data={"distance_km": "10", "duration_seconds": "3000"},
        files=[
            ("images", ("date.png", b"img-a", "image/png")),
            ("images", ("track.png", b"img-b", "image/png")),
        ],
    )
    assert r.status_code == 201, r.text
    assert len(r.json()["screenshots"]) == 2

    rec = await session.scalar(
        select(AttendanceRecord).where(AttendanceRecord.runner_id == runner.id)
    )
    assert rec is not None
    await session.refresh(rec, attribute_names=["result"])
    assert rec.result is not None
    assert len(rec.result.screenshots or []) == 2
