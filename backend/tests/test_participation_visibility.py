from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, ModerationStatus, UserRole
from app.models.event import Event
from app.models.group import Group
from app.models.result import Result
from tests.factories import make_attendance_with_result, make_event_group, make_user


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def _protocol_names(body: dict) -> list[str]:
    rows = body["finishers"] + body["pending"] + body["dnf"]
    return [r["display_name"] for r in rows]


async def _self_reported(
    session: AsyncSession, group: Group, email: str, moderation: ModerationStatus
) -> tuple:
    runner = await make_user(session, email)
    rec = await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=moderation,
        self_reported=True,
    )
    return runner, rec


# ---- is_past / has_started ---------------------------------------------------


@pytest.mark.asyncio
async def test_event_and_group_expose_server_computed_time_flags(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-flags@e.com", UserRole.organizer)
    past_event, past_group = await make_event_group(session, org)  # 2026-05-01
    future_event = Event(title="Later", date=date(2099, 1, 1), created_by=org.id)
    session.add(future_event)
    await session.flush()
    future_group = Group(
        event_id=future_event.id,
        location="L",
        name="X-10",
        target_distance_km=10.0,
        start_time=datetime(2099, 1, 1, 6, 0, tzinfo=UTC),
    )
    session.add(future_group)
    await session.commit()

    assert (await client.get(f"/api/v1/events/{past_event.id}")).json()["is_past"] is True
    assert (await client.get(f"/api/v1/events/{future_event.id}")).json()["is_past"] is False
    listed = (await client.get("/api/v1/events")).json()["items"]
    assert {e["id"]: e["is_past"] for e in listed} == {
        past_event.id: True,
        future_event.id: False,
    }
    assert (await client.get(f"/api/v1/groups/{past_group.id}")).json()["has_started"] is True
    assert (await client.get(f"/api/v1/groups/{future_group.id}")).json()["has_started"] is False


# ---- participation state -----------------------------------------------------


@pytest.mark.asyncio
async def test_participation_states(session: AsyncSession, client: AsyncClient) -> None:
    org = await make_user(session, "org-part@e.com", UserRole.organizer)
    event, group = await make_event_group(session, org)
    other = Group(
        event_id=event.id,
        location="L",
        name="D-21",
        distance_code="D-21",
        target_distance_km=21.0,
        start_time=group.start_time,
    )
    session.add(other)

    nobody = await make_user(session, "part-none@e.com")
    on_protocol = await make_user(session, "part-proto@e.com")
    session.add(
        AttendanceRecord(
            group_id=group.id,
            raw_name="P",
            runner_id=on_protocol.id,
            finish_status=FinishStatus.finished,
        )
    )
    pending, _ = await _self_reported(session, group, "part-pend@e.com", ModerationStatus.pending)
    approved, _ = await _self_reported(session, group, "part-appr@e.com", ModerationStatus.approved)
    rejected, _ = await _self_reported(session, group, "part-rej@e.com", ModerationStatus.rejected)
    await session.commit()

    async def state(user_id: int, group_id: int) -> dict:
        r = await client.get(f"/api/v1/groups/{group_id}/participation/me", headers=_auth(user_id))
        assert r.status_code == 200, r.text
        return r.json()

    assert (await state(nobody.id, group.id))["status"] == "none"
    assert (await state(on_protocol.id, group.id))["status"] == "in_protocol"
    assert (await state(pending.id, group.id))["status"] == "pending"
    assert (await state(approved.id, group.id))["status"] == "approved"
    assert (await state(rejected.id, group.id))["status"] == "rejected"

    conflict = await state(pending.id, other.id)
    assert conflict["status"] == "other_group"
    assert conflict["other_group_name"] == "X-10"


@pytest.mark.asyncio
async def test_participation_requires_login(session: AsyncSession, client: AsyncClient) -> None:
    org = await make_user(session, "org-part-anon@e.com", UserRole.organizer)
    _event, group = await make_event_group(session, org)
    await session.commit()
    assert (await client.get(f"/api/v1/groups/{group.id}/participation/me")).status_code == 401


# ---- deep link into the profile's "Загрузить результат" section --------------


@pytest.mark.asyncio
async def test_awaiting_results_can_include_an_unsigned_group(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-incl@e.com", UserRole.organizer)
    _event, group = await make_event_group(session, org)
    runner = await make_user(session, "run-incl@e.com")  # never signed up
    await session.commit()
    url = "/api/v1/users/me/signups/awaiting-result"

    assert (await client.get(url, headers=_auth(runner.id))).json() == []

    included = (
        await client.get(url, params={"include_group_id": group.id}, headers=_auth(runner.id))
    ).json()
    assert len(included) == 1
    assert included[0]["group_id"] == group.id
    assert included[0]["signup_id"] is None
    assert included[0]["has_result"] is False


@pytest.mark.asyncio
async def test_awaiting_results_include_skips_unstarted_and_settled_groups(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-incl2@e.com", UserRole.organizer)
    _event, started = await make_event_group(session, org)
    future_event = Event(title="Later", date=date(2099, 1, 1), created_by=org.id)
    session.add(future_event)
    await session.flush()
    future = Group(
        event_id=future_event.id,
        location="L",
        name="X-10",
        target_distance_km=10.0,
        start_time=datetime(2099, 1, 1, 6, 0, tzinfo=UTC),
    )
    session.add(future)
    runner, _rec = await _self_reported(
        session, started, "run-incl2@e.com", ModerationStatus.approved
    )
    await session.commit()
    url = "/api/v1/users/me/signups/awaiting-result"

    not_started = await client.get(
        url, params={"include_group_id": future.id}, headers=_auth(runner.id)
    )
    assert not_started.json() == []
    approved = await client.get(
        url, params={"include_group_id": started.id}, headers=_auth(runner.id)
    )
    assert approved.json() == []


# ---- unmoderated self-reports stay private -----------------------------------


@pytest.mark.asyncio
async def test_protocol_hides_an_unapproved_self_report_from_others(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-prot@e.com", UserRole.organizer)
    _event, group = await make_event_group(session, org)
    reporter, rec = await _self_reported(
        session, group, "prot-reporter@e.com", ModerationStatus.pending
    )
    viewer = await make_user(session, "prot-viewer@e.com")
    admin = await make_user(session, "prot-admin@e.com", UserRole.admin)
    await session.commit()
    url = f"/api/v1/groups/{group.id}/protocol"
    name = f"{reporter.first_name} {reporter.last_name}"

    assert name not in _protocol_names((await client.get(url, headers=_auth(viewer.id))).json())
    assert name in _protocol_names((await client.get(url, headers=_auth(reporter.id))).json())
    assert name in _protocol_names((await client.get(url, headers=_auth(admin.id))).json())

    result = await session.scalar(select(Result).where(Result.attendance_record_id == rec.id))
    assert result is not None
    result.status = ModerationStatus.approved
    await session.commit()
    assert name in _protocol_names((await client.get(url, headers=_auth(viewer.id))).json())


@pytest.mark.asyncio
async def test_history_hides_an_unapproved_self_report_from_others(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-hist@e.com", UserRole.organizer)
    _event, group = await make_event_group(session, org)
    reporter, _rec = await _self_reported(
        session, group, "hist-reporter@e.com", ModerationStatus.pending
    )
    viewer = await make_user(session, "hist-viewer@e.com")
    admin = await make_user(session, "hist-admin@e.com", UserRole.admin)
    await session.commit()
    url = f"/api/v1/users/{reporter.id}/history"

    assert (await client.get(url)).json()["total"] == 0
    assert (await client.get(url, headers=_auth(viewer.id))).json()["total"] == 0
    assert (await client.get(url, headers=_auth(reporter.id))).json()["total"] == 1
    assert (await client.get(url, headers=_auth(admin.id))).json()["total"] == 1


@pytest.mark.asyncio
async def test_profile_stats_ignore_an_unapproved_self_report(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-stat@e.com", UserRole.organizer)
    _event, group = await make_event_group(session, org)
    reporter, rec = await _self_reported(
        session, group, "stat-reporter@e.com", ModerationStatus.pending
    )
    viewer = await make_user(session, "stat-viewer@e.com")
    await session.commit()
    url = f"/api/v1/users/{reporter.id}"

    before = (await client.get(url, headers=_auth(viewer.id))).json()
    assert before["total_runs_count"] == 0
    assert before["rating"] == 0
    assert before["current_streak"] == 0

    result = await session.scalar(select(Result).where(Result.attendance_record_id == rec.id))
    assert result is not None
    result.status = ModerationStatus.approved
    await session.commit()

    after = (await client.get(url, headers=_auth(viewer.id))).json()
    assert after["total_runs_count"] == 1
    assert after["rating"] == 1


# ---- signed up for one group, ran in another ---------------------------------


async def _two_groups(session: AsyncSession, org_email: str) -> tuple[Group, Group]:
    org = await make_user(session, org_email, UserRole.organizer)
    event, group_x = await make_event_group(session, org)  # X-10
    group_d = Group(
        event_id=event.id,
        location="L",
        name="D-21",
        distance_code="D-21",
        target_distance_km=21.0,
        start_time=group_x.start_time,
    )
    session.add(group_d)
    await session.flush()
    return group_d, group_x


@pytest.mark.asyncio
async def test_signup_follows_the_run_into_the_group_actually_run(
    session: AsyncSession, client: AsyncClient
) -> None:
    from app.models.signup import Signup

    group_d, group_x = await _two_groups(session, "org-move@e.com")
    runner = await make_user(session, "run-move@e.com")
    session.add(Signup(runner_id=runner.id, group_id=group_d.id, event_id=group_d.event_id))
    await session.commit()

    r = await client.post(
        f"/api/v1/groups/{group_x.id}/result",
        headers=_auth(runner.id),
        data={"distance_km": "10", "duration_seconds": "3000"},
        files={"images": ("s.png", b"fake", "image/png")},
    )
    assert r.status_code == 201, r.text
    signup = await session.scalar(select(Signup).where(Signup.runner_id == runner.id))
    await session.refresh(signup)
    assert signup.group_id == group_x.id


@pytest.mark.asyncio
async def test_awaiting_entry_follows_the_protocol_group_not_the_signup(
    session: AsyncSession, client: AsyncClient
) -> None:
    from app.models.signup import Signup

    group_d, group_x = await _two_groups(session, "org-await@e.com")
    runner = await make_user(session, "run-await@e.com")
    session.add(Signup(runner_id=runner.id, group_id=group_d.id, event_id=group_d.event_id))
    session.add(
        AttendanceRecord(
            group_id=group_x.id,
            raw_name="R",
            runner_id=runner.id,
            finish_status=FinishStatus.finished,
        )
    )
    await session.commit()
    url = "/api/v1/users/me/signups/awaiting-result"

    entries = (await client.get(url, headers=_auth(runner.id))).json()
    assert len(entries) == 1
    assert entries[0]["group_id"] == group_x.id  # where the protocol has them
    assert entries[0]["has_record"] is True


@pytest.mark.asyncio
async def test_awaiting_entry_without_a_record_keeps_the_signed_group_and_allows_switching(
    session: AsyncSession, client: AsyncClient
) -> None:
    from app.models.signup import Signup

    group_d, _group_x = await _two_groups(session, "org-await2@e.com")
    runner = await make_user(session, "run-await2@e.com")
    session.add(Signup(runner_id=runner.id, group_id=group_d.id, event_id=group_d.event_id))
    await session.commit()

    entries = (
        await client.get("/api/v1/users/me/signups/awaiting-result", headers=_auth(runner.id))
    ).json()
    assert [e["group_id"] for e in entries] == [group_d.id]
    assert entries[0]["has_record"] is False


@pytest.mark.asyncio
async def test_rejected_record_in_another_group_does_not_block_switching(
    session: AsyncSession, client: AsyncClient
) -> None:
    """The actual bug report: a runner rejected in X-10 (wrong group) must be
    able to submit into D-21 instead — not get told they "already have a
    result" with no way out other than support."""
    from app.models.signup import Signup

    group_d, group_x = await _two_groups(session, "org-fix1@e.com")
    runner, rec = await _self_reported(
        session, group_x, "run-fix1@e.com", ModerationStatus.rejected
    )
    session.add(Signup(runner_id=runner.id, group_id=group_x.id, event_id=group_x.event_id))
    await session.commit()

    # She can't switch to a group that's still fixed for her, but a rejected
    # one shows up switchable in her "Загрузить результат" list.
    entries = (
        await client.get("/api/v1/users/me/signups/awaiting-result", headers=_auth(runner.id))
    ).json()
    assert len(entries) == 1
    assert entries[0]["group_id"] == group_x.id
    assert entries[0]["has_record"] is False  # switcher visible

    # The group page for D-21 must also offer resubmission, not "other_group".
    state = (
        await client.get(f"/api/v1/groups/{group_d.id}/participation/me", headers=_auth(runner.id))
    ).json()
    assert state["status"] == "rejected"

    resp = await client.post(
        f"/api/v1/groups/{group_d.id}/result",
        headers=_auth(runner.id),
        data={"distance_km": "21", "duration_seconds": "6000"},
        files={"images": ("s.png", b"fake", "image/png")},
    )
    assert resp.status_code == 201, resp.text

    # The *same* record moved groups — no orphaned duplicate in X-10.
    records = list(
        await session.scalars(
            select(AttendanceRecord).where(AttendanceRecord.runner_id == runner.id)
        )
    )
    assert [r.id for r in records] == [rec.id]
    await session.refresh(rec)
    assert rec.group_id == group_d.id
    result = await session.scalar(select(Result).where(Result.attendance_record_id == rec.id))
    assert result is not None and result.status == ModerationStatus.pending

    # The signup followed it too.
    signup = await session.scalar(select(Signup).where(Signup.runner_id == runner.id))
    await session.refresh(signup)
    assert signup.group_id == group_d.id


@pytest.mark.asyncio
async def test_pending_record_in_another_group_still_blocks_switching(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Only a *rejected* record is reusable — one still awaiting review stays
    a hard conflict, same as before (see _check_resubmit_allowed's own-record
    rule: don't let a runner change what's mid-review)."""
    group_d, group_x = await _two_groups(session, "org-fix2@e.com")
    runner, _rec = await _self_reported(
        session, group_x, "run-fix2@e.com", ModerationStatus.pending
    )
    await session.commit()

    state = (
        await client.get(f"/api/v1/groups/{group_d.id}/participation/me", headers=_auth(runner.id))
    ).json()
    assert state["status"] == "other_group"

    resp = await client.post(
        f"/api/v1/groups/{group_d.id}/result",
        headers=_auth(runner.id),
        data={"distance_km": "21", "duration_seconds": "6000"},
        files={"images": ("s.png", b"fake", "image/png")},
    )
    assert resp.status_code == 409
