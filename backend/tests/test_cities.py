import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.city import City
from app.models.profile_edit_request import ProfileEditRequest
from app.services.profile_review_service import approve
from tests.factories import make_user


def _city(cid: int, name: str, ascii_name: str, population: int, region: str | None = None) -> City:
    return City(
        id=cid,
        name=name,
        name_ascii=ascii_name,
        search_name=name.lower(),
        search_ascii=ascii_name.lower(),
        country_code="RU",
        country="Россия",
        region=region,
        lat=55.0,
        lng=47.0,
        population=population,
    )


@pytest.mark.asyncio
async def test_city_search_matches_cyrillic_and_latin_and_ranks_by_population(
    session: AsyncSession, client: AsyncClient
) -> None:
    session.add_all(
        [
            _city(1, "Чебоксары", "Cheboksary", 492331, "Чувашия"),
            _city(2, "Чебоксары", "Cheboksary", 5000, "Тамбовская обл."),
            _city(3, "Москва", "Moscow", 10000000, "Москва"),
            _city(4, "Набережные Челны", "Naberezhnye Chelny", 533839, "Татарстан"),
        ]
    )
    await session.commit()

    # Cyrillic prefix, case-insensitive; biggest first.
    r = await client.get("/api/v1/cities/search", params={"q": "чебокс", "limit": 5})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data[0]["name"] == "Чебоксары"
    assert data[0]["region"] == "Чувашия"

    # Mid-word match: "челны" finds "Набережные Челны".
    r_mid = await client.get("/api/v1/cities/search", params={"q": "челны"})
    assert [c["name"] for c in r_mid.json()] == ["Набережные Челны"]

    # Latin name of a Cyrillic city also matches.
    r2 = await client.get("/api/v1/cities/search", params={"q": "mosc"})
    assert r2.json()[0]["name"] == "Москва"

    # Too-short queries are rejected by validation.
    assert (await client.get("/api/v1/cities/search", params={"q": "ч"})).status_code == 422


@pytest.mark.asyncio
async def test_update_profile_city_id_mirrors_name(
    session: AsyncSession, client: AsyncClient
) -> None:
    """city_id/city are post-moderated (see ProfileEditRequest) — the PATCH
    stages the pick without touching the account, and the canonical-name
    mirroring only happens once an admin approves it (see
    profile_review_service.approve)."""
    runner = await make_user(session, "city-picker@example.com")
    session.add(_city(10, "Казань", "Kazan", 1200000, "Татарстан"))
    await session.commit()
    token = create_access_token(runner.id)

    r = await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"city_id": 10},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["city_id"] is None  # not applied yet
    assert body["pending_review"]["changes"]["city_id"] == 10

    request = await session.scalar(
        select(ProfileEditRequest).where(ProfileEditRequest.user_id == runner.id)
    )
    assert request is not None
    await approve(session, request)
    await session.commit()
    await session.refresh(runner)
    assert runner.city_id == 10
    assert runner.city == "Казань"  # server mirrored the canonical name
