import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.profile_edit_request import ProfileEditRequest
from app.models.running_club import RunningClub
from app.services.profile_review_service import approve
from app.services.running_club_service import ensure_running_club
from tests.factories import make_user


@pytest.mark.asyncio
async def test_ensure_running_club_creates_and_dedupes(session: AsyncSession) -> None:
    a = await ensure_running_club(session, "Бегуны Чебоксар")
    assert a is not None
    assert a.title == "Бегуны Чебоксар"
    assert a.city is None

    # Same name, different casing/whitespace → same row, no duplicate.
    b = await ensure_running_club(session, "  бегуны чебоксар ")
    assert b is not None and b.id == a.id

    # Empty / "not in a club" answers create nothing.
    assert await ensure_running_club(session, "") is None
    assert await ensure_running_club(session, None) is None

    await session.commit()
    assert await session.scalar(select(func.count(RunningClub.id))) == 1


@pytest.mark.asyncio
async def test_search_running_clubs(session: AsyncSession, client: AsyncClient) -> None:
    await ensure_running_club(session, "Бегуны Чебоксар")
    await ensure_running_club(session, "Марафонцы Казани")
    await session.commit()

    resp = await client.get("/api/v1/running-clubs/search", params={"q": "бегун"})
    assert resp.status_code == 200
    titles = [c["title"] for c in resp.json()]
    assert "Бегуны Чебоксар" in titles
    assert "Марафонцы Казани" not in titles


@pytest.mark.asyncio
async def test_search_running_clubs_blank_query_lists_all(
    session: AsyncSession, client: AsyncClient
) -> None:
    """A blank q lists every club instead of nothing — powers the picker
    showing options as soon as the field gains focus, before typing."""
    await ensure_running_club(session, "Бегуны Чебоксар")
    await ensure_running_club(session, "Марафонцы Казани")
    await session.commit()

    resp = await client.get("/api/v1/running-clubs/search")
    assert resp.status_code == 200
    titles = [c["title"] for c in resp.json()]
    assert "Бегуны Чебоксар" in titles
    assert "Марафонцы Казани" in titles


async def _approve_pending(session: AsyncSession, user_id: int) -> None:
    request = await session.scalar(
        select(ProfileEditRequest)
        .where(ProfileEditRequest.user_id == user_id, ProfileEditRequest.status == "pending")
        .order_by(ProfileEditRequest.id.desc())
    )
    assert request is not None
    await approve(session, request)
    await session.commit()


@pytest.mark.asyncio
async def test_profile_update_adds_and_canonicalizes_club(
    session: AsyncSession, client: AsyncClient
) -> None:
    """running_club is post-moderated (see ProfileEditRequest) — the
    dictionary lookup/creation and canonical-spelling rewrite only happen
    once an admin approves the staged change (see
    profile_review_service.approve)."""
    runner = await make_user(session, "clubby@example.com")
    await ensure_running_club(session, "Гончие Псы")  # already listed
    await session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(runner.id)}"}

    # A brand-new club is added to the dictionary (empty city) once approved.
    r1 = await client.patch(
        "/api/v1/users/me", headers=headers, json={"running_club": "Новый Клуб"}
    )
    assert r1.status_code == 200
    assert r1.json()["pending_review"]["changes"]["running_club"] == "Новый Клуб"
    await _approve_pending(session, runner.id)
    await session.refresh(runner)
    assert runner.running_club == "Новый Клуб"
    created = await session.scalar(select(RunningClub).where(RunningClub.title == "Новый Клуб"))
    assert created is not None and created.city is None

    # Typing an existing club in a different case stores it under its canonical spelling.
    r2 = await client.patch(
        "/api/v1/users/me", headers=headers, json={"running_club": "гончие псы"}
    )
    assert r2.status_code == 200
    assert r2.json()["pending_review"]["changes"]["running_club"] == "гончие псы"
    await _approve_pending(session, runner.id)
    await session.refresh(runner)
    assert runner.running_club == "Гончие Псы"
