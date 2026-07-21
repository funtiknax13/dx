import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.attendance import AttendanceRecord
from app.models.enums import UserRole
from app.services.safe_fetch import FetchError
from tests.factories import make_event_group, make_user

SAMPLE_GPX = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>Test</name><trkseg>
    <trkpt lat="55.7500" lon="37.6200"><ele>150.0</ele><time>2026-05-01T08:00:00Z</time></trkpt>
    <trkpt lat="55.7510" lon="37.6210"><ele>152.0</ele><time>2026-05-01T08:05:00Z</time></trkpt>
    <trkpt lat="55.7520" lon="37.6220"><ele>151.0</ele><time>2026-05-01T08:35:00Z</time></trkpt>
  </trkseg></trk>
</gpx>
"""


async def _make_matched_attendance(
    session: AsyncSession, runner, target_km: float = 10.0
) -> AttendanceRecord:
    org = await make_user(session, f"org-importurl-{runner.id}@example.com", UserRole.organizer)
    _, group = await make_event_group(session, org, target_km=target_km)
    record = AttendanceRecord(
        group_id=group.id, raw_name=f"{runner.first_name} {runner.last_name}", runner_id=runner.id
    )
    session.add(record)
    await session.flush()
    return record


@pytest.mark.asyncio
async def test_import_url_creates_result_from_fetched_gpx(
    session: AsyncSession, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = await make_user(session, "runner-importurl1@example.com")
    record = await _make_matched_attendance(session, runner)
    await session.commit()

    async def fake_fetch(url: str) -> tuple[bytes, str, str]:
        assert url == "https://watch.example.com/export/abc"
        return SAMPLE_GPX, "application/gpx+xml", ""

    monkeypatch.setattr("app.api.results.fetch_external_workout_file", fake_fetch)

    token = create_access_token(runner.id)
    resp = await client.post(
        f"/api/v1/attendance/{record.id}/result/import-url",
        headers={"Authorization": f"Bearer {token}"},
        json={"url": "https://watch.example.com/export/abc"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"] == "file"
    assert body["source_file"] is not None
    # The GPX's own track is ~250m — way off the group's 10km target, so the
    # measured distance isn't trusted: falls back to the group's reference
    # distance, keeps the file's real duration, and needs moderation.
    assert body["distance_km"] == 10.0
    assert body["duration_seconds"] == 2100
    assert body["status"] == "pending"
    # finish_status mirrors the protocol (AttendanceRecord default), not
    # something computed from the (unreliable) measured distance.
    assert body["finish_status"] == "finished"


@pytest.mark.asyncio
async def test_import_url_uses_measured_distance_when_within_tolerance(
    session: AsyncSession, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = await make_user(session, "runner-importurl1b@example.com")
    # Target close to the GPX's real ~0.25km track so it's within tolerance.
    record = await _make_matched_attendance(session, runner, target_km=0.25)
    await session.commit()

    async def fake_fetch(url: str) -> tuple[bytes, str, str]:
        return SAMPLE_GPX, "application/gpx+xml", ""

    monkeypatch.setattr("app.api.results.fetch_external_workout_file", fake_fetch)

    token = create_access_token(runner.id)
    resp = await client.post(
        f"/api/v1/attendance/{record.id}/result/import-url",
        headers={"Authorization": f"Bearer {token}"},
        json={"url": "https://watch.example.com/export/abc"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["distance_km"] != 0.25  # the actual measured distance, not the target
    assert body["distance_km"] > 0


@pytest.mark.asyncio
async def test_import_url_rejects_unrecognized_format(
    session: AsyncSession, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = await make_user(session, "runner-importurl2@example.com")
    record = await _make_matched_attendance(session, runner)
    await session.commit()

    async def fake_fetch(url: str) -> tuple[bytes, str, str]:
        return b"not a track file", "text/plain", ""

    monkeypatch.setattr("app.api.results.fetch_external_workout_file", fake_fetch)

    token = create_access_token(runner.id)
    resp = await client.post(
        f"/api/v1/attendance/{record.id}/result/import-url",
        headers={"Authorization": f"Bearer {token}"},
        json={"url": "https://watch.example.com/export/abc"},
    )
    assert resp.status_code == 400
    assert "GPX or FIT" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_import_url_translates_fetch_error_to_400(
    session: AsyncSession, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers the SSRF-rejection path (private IP, non-https, etc.) without
    depending on real DNS/network state in the test run — safe_fetch's own
    validation logic is covered directly in test_safe_fetch.py."""
    runner = await make_user(session, "runner-importurl3@example.com")
    record = await _make_matched_attendance(session, runner)
    await session.commit()

    async def fake_fetch(url: str) -> tuple[bytes, str, str]:
        raise FetchError("That link points to a disallowed address")

    monkeypatch.setattr("app.api.results.fetch_external_workout_file", fake_fetch)

    token = create_access_token(runner.id)
    resp = await client.post(
        f"/api/v1/attendance/{record.id}/result/import-url",
        headers={"Authorization": f"Bearer {token}"},
        json={"url": "https://127.0.0.1/export.gpx"},
    )
    assert resp.status_code == 400
    assert "disallowed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_import_url_requires_matched_account(
    session: AsyncSession, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await make_user(session, "admin-importurl4@example.com", UserRole.admin)
    org = await make_user(session, "org-importurl4@example.com", UserRole.organizer)
    _, group = await make_event_group(session, org)
    record = AttendanceRecord(group_id=group.id, raw_name="Unmatched Runner", runner_id=None)
    session.add(record)
    await session.commit()

    async def fake_fetch(url: str) -> tuple[bytes, str, str]:
        return SAMPLE_GPX, "application/gpx+xml", ""

    monkeypatch.setattr("app.api.results.fetch_external_workout_file", fake_fetch)

    token = create_access_token(admin.id)
    resp = await client.post(
        f"/api/v1/attendance/{record.id}/result/import-url",
        headers={"Authorization": f"Bearer {token}"},
        json={"url": "https://watch.example.com/export/abc"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_import_url_forbidden_for_a_different_runner(
    session: AsyncSession, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await make_user(session, "runner-importurl5@example.com")
    other = await make_user(session, "runner-importurl6@example.com")
    record = await _make_matched_attendance(session, owner)
    await session.commit()

    async def fake_fetch(url: str) -> tuple[bytes, str, str]:
        return SAMPLE_GPX, "application/gpx+xml", ""

    monkeypatch.setattr("app.api.results.fetch_external_workout_file", fake_fetch)

    token = create_access_token(other.id)
    resp = await client.post(
        f"/api/v1/attendance/{record.id}/result/import-url",
        headers={"Authorization": f"Bearer {token}"},
        json={"url": "https://watch.example.com/export/abc"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_resubmit_blocked_while_pending(
    session: AsyncSession, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A runner can't just keep re-attempting while their first submission is
    sitting in the moderation queue — see _check_no_pending_result."""
    runner = await make_user(session, "runner-importurl7@example.com")
    record = await _make_matched_attendance(session, runner)  # target 10km, GPX ~0.25km -> pending
    await session.commit()

    async def fake_fetch(url: str) -> tuple[bytes, str, str]:
        return SAMPLE_GPX, "application/gpx+xml", ""

    monkeypatch.setattr("app.api.results.fetch_external_workout_file", fake_fetch)
    token = create_access_token(runner.id)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"url": "https://watch.example.com/export/abc"}

    first = await client.post(
        f"/api/v1/attendance/{record.id}/result/import-url", headers=headers, json=payload
    )
    assert first.status_code == 201
    assert first.json()["status"] == "pending"

    second = await client.post(
        f"/api/v1/attendance/{record.id}/result/import-url", headers=headers, json=payload
    )
    assert second.status_code == 409
    assert "проверки" in second.json()["detail"]


@pytest.mark.asyncio
async def test_admin_can_resubmit_even_while_pending(
    session: AsyncSession, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = await make_user(session, "runner-importurl8@example.com")
    admin = await make_user(session, "admin-importurl8@example.com", UserRole.admin)
    record = await _make_matched_attendance(session, runner)
    await session.commit()

    async def fake_fetch(url: str) -> tuple[bytes, str, str]:
        return SAMPLE_GPX, "application/gpx+xml", ""

    monkeypatch.setattr("app.api.results.fetch_external_workout_file", fake_fetch)
    payload = {"url": "https://watch.example.com/export/abc"}

    runner_token = create_access_token(runner.id)
    first = await client.post(
        f"/api/v1/attendance/{record.id}/result/import-url",
        headers={"Authorization": f"Bearer {runner_token}"},
        json=payload,
    )
    assert first.status_code == 201
    result_id = first.json()["id"]

    admin_token = create_access_token(admin.id)
    second = await client.post(
        f"/api/v1/attendance/{record.id}/result/import-url",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=payload,
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] == result_id


@pytest.mark.asyncio
async def test_resubmit_allowed_again_once_approved(
    session: AsyncSession, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.models.enums import ModerationStatus
    from app.models.result import Result

    runner = await make_user(session, "runner-importurl9@example.com")
    record = await _make_matched_attendance(session, runner)
    await session.commit()

    async def fake_fetch(url: str) -> tuple[bytes, str, str]:
        return SAMPLE_GPX, "application/gpx+xml", ""

    monkeypatch.setattr("app.api.results.fetch_external_workout_file", fake_fetch)
    token = create_access_token(runner.id)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"url": "https://watch.example.com/export/abc"}

    first = await client.post(
        f"/api/v1/attendance/{record.id}/result/import-url", headers=headers, json=payload
    )
    assert first.status_code == 201

    result = await session.scalar(
        select(Result).where(Result.attendance_record_id == record.id)
    )
    assert result is not None
    result.status = ModerationStatus.approved
    await session.commit()

    second = await client.post(
        f"/api/v1/attendance/{record.id}/result/import-url", headers=headers, json=payload
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] == result.id
