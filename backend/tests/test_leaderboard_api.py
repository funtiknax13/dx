import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, UserRole
from tests.factories import make_event_group, make_user


async def _finish_n(session: AsyncSession, group, runner_id: int, n: int) -> None:
    for _ in range(n):
        session.add(
            AttendanceRecord(
                group_id=group.id,
                raw_name="Runner",
                runner_id=runner_id,
                finish_status=FinishStatus.finished,
            )
        )
    await session.flush()


@pytest.mark.asyncio
async def test_leaderboard_top_n_and_me_row(
    session: AsyncSession, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.api.leaderboard as leaderboard_module

    monkeypatch.setattr(leaderboard_module, "TOP_N", 2)

    org = await make_user(session, "org-ltop@example.com", UserRole.organizer)
    r1 = await make_user(session, "r1-ltop@example.com")
    r2 = await make_user(session, "r2-ltop@example.com")
    r3 = await make_user(session, "r3-ltop@example.com")
    _, group = await make_event_group(session, org)

    await _finish_n(session, group, r1.id, 3)
    await _finish_n(session, group, r2.id, 2)
    await _finish_n(session, group, r3.id, 1)
    await session.commit()

    # Anonymous: leaderboard is gated too (see profile_completeness_service).
    resp = await client.get("/api/v1/leaderboard", params={"metric": "dx"})
    body = resp.json()
    assert body["lock_reason"] == "anonymous"
    assert body["entries"] == []
    assert body["me"] is None

    token3 = create_access_token(r3.id)
    resp3 = await client.get(
        "/api/v1/leaderboard",
        params={"metric": "dx"},
        headers={"Authorization": f"Bearer {token3}"},
    )
    body3 = resp3.json()
    assert body3["lock_reason"] is None
    assert [e["runner_id"] for e in body3["entries"]] == [r1.id, r2.id]
    assert body3["me"]["runner_id"] == r3.id
    assert body3["me"]["rank"] == 3


@pytest.mark.asyncio
async def test_leaderboard_locked_for_incomplete_profile(
    session: AsyncSession, client: AsyncClient
) -> None:
    runner = await make_user(session, "incomplete-lb@example.com", complete_profile=False)
    await session.commit()

    token = create_access_token(runner.id)
    resp = await client.get(
        "/api/v1/leaderboard",
        params={"metric": "streak"},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.json()
    assert body["lock_reason"] == "profile_incomplete"
    assert body["entries"] == []
