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
async def test_rating_top_n_and_me_row(
    session: AsyncSession, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.api.rating as rating_module

    monkeypatch.setattr(rating_module, "TOP_N", 2)

    org = await make_user(session, "org-rtop@example.com", UserRole.organizer)
    r1 = await make_user(session, "r1-rtop@example.com")
    r2 = await make_user(session, "r2-rtop@example.com")
    r3 = await make_user(session, "r3-rtop@example.com")
    _, group = await make_event_group(session, org)

    # Distinct AttendanceRecord counts require distinct groups per finish
    # since attendance is one row per run — reuse the same group, it's fine,
    # counts_toward_rating defaults True.
    await _finish_n(session, group, r1.id, 3)
    await _finish_n(session, group, r2.id, 2)
    await _finish_n(session, group, r3.id, 1)
    await session.commit()

    # Anonymous: only top 2 (TOP_N), no "me".
    resp = await client.get("/api/v1/rating")
    body = resp.json()
    assert [e["runner_id"] for e in body["entries"]] == [r1.id, r2.id]
    assert body["me"] is None

    # r3 is rank 3, outside top 2 -> gets a "me" row.
    token3 = create_access_token(r3.id)
    resp3 = await client.get("/api/v1/rating", headers={"Authorization": f"Bearer {token3}"})
    body3 = resp3.json()
    assert body3["me"]["runner_id"] == r3.id
    assert body3["me"]["rank"] == 3

    # r1 is rank 1, already in entries -> "me" stays None (no duplicate row).
    token1 = create_access_token(r1.id)
    resp1 = await client.get("/api/v1/rating", headers={"Authorization": f"Bearer {token1}"})
    assert resp1.json()["me"] is None


@pytest.mark.asyncio
async def test_rating_invalid_token_is_treated_as_anonymous(
    session: AsyncSession, client: AsyncClient
) -> None:
    resp = await client.get("/api/v1/rating", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 200
    assert resp.json()["me"] is None
