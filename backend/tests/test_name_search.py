import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.guest_service import create_guest
from app.services.name_search import flexible_name_filter
from tests.factories import make_user


@pytest.mark.asyncio
async def test_single_word_matches_first_or_last_name(session: AsyncSession) -> None:
    ivan = await make_user(session, "ivan-petrov@example.com")
    ivan.first_name, ivan.last_name = "Иван", "Петров"
    other = await make_user(session, "other-name@example.com")
    other.first_name, other.last_name = "Мария", "Сидорова"
    await session.commit()

    # Case-insensitive Cyrillic matching itself (e.g. "иван" -> "Иван") relies
    # on ILIKE's lower(), which SQLite (used here) only case-folds for ASCII
    # — Postgres handles Unicode correctly (verified manually against dev).
    # These queries match the stored casing, keeping the test focused on the
    # actual bug (single vs. combined word matching), not case-folding.
    for query in ("Иван", "Петров", "Петр"):
        result = list(
            await session.scalars(select(User).where(flexible_name_filter(query)))
        )
        assert ivan.id in {u.id for u in result}, f"query={query!r} should match Иван Петров"
        assert other.id not in {u.id for u in result}


@pytest.mark.asyncio
async def test_two_word_query_matches_first_and_last_name_together(
    session: AsyncSession,
) -> None:
    """The actual bug report: searching "Иван Петров" (both words at once)
    against a single ILIKE'd column never matches, since neither first_name
    nor last_name alone contains the full two-word string."""
    ivan = await make_user(session, "ivan-petrov2@example.com")
    ivan.first_name, ivan.last_name = "Иван", "Петров"
    await session.commit()

    result = list(
        await session.scalars(select(User).where(flexible_name_filter("Иван Петров")))
    )
    assert ivan.id in {u.id for u in result}


@pytest.mark.asyncio
async def test_two_word_query_matches_regardless_of_order(session: AsyncSession) -> None:
    ivan = await make_user(session, "ivan-petrov3@example.com")
    ivan.first_name, ivan.last_name = "Иван", "Петров"
    await session.commit()

    result = list(
        await session.scalars(select(User).where(flexible_name_filter("Петров Иван")))
    )
    assert ivan.id in {u.id for u in result}


@pytest.mark.asyncio
async def test_two_word_query_does_not_match_unrelated_person(session: AsyncSession) -> None:
    await make_user(session, "unrelated@example.com")
    other = await make_user(session, "unrelated2@example.com")
    other.first_name, other.last_name = "Мария", "Сидорова"
    await session.commit()

    result = list(
        await session.scalars(select(User).where(flexible_name_filter("Иван Петров")))
    )
    assert other.id not in {u.id for u in result}


@pytest.mark.asyncio
async def test_single_word_matches_email_when_included(session: AsyncSession) -> None:
    # A name unrelated to the email's local part — make_user derives
    # last_name from the email prefix by default, which would otherwise
    # match "findme" via the name columns regardless of include_email.
    user = await make_user(session, "findme@example.com")
    user.first_name, user.last_name = "Алексей", "Кузнецов"
    await session.commit()

    with_email = list(
        await session.scalars(
            select(User).where(flexible_name_filter("findme", include_email=True))
        )
    )
    assert user.id in {u.id for u in with_email}

    without_email = list(
        await session.scalars(
            select(User).where(flexible_name_filter("findme", include_email=False))
        )
    )
    assert user.id not in {u.id for u in without_email}


@pytest.mark.asyncio
async def test_guests_search_api_matches_first_and_last_name_together(
    session: AsyncSession, client: AsyncClient
) -> None:
    guest = await create_guest(session, "Иван Петров")
    await session.commit()

    resp = await client.get("/api/v1/guests", params={"q": "Иван Петров"})
    assert resp.status_code == 200, resp.text
    assert guest.id in {g["id"] for g in resp.json()}

