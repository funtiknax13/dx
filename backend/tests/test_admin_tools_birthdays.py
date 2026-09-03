from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.tools_birthdays import MONTH_NAMES, _next_occurrence
from app.core.security import create_access_token
from app.models.enums import UserRole
from tests.factories import make_user


async def _login(client: AsyncClient, user_id: int) -> None:
    token = create_access_token(user_id)
    resp = await client.get(f"/admin-tools/sso?token={token}", follow_redirects=False)
    assert resp.status_code == 302


def test_next_occurrence_later_this_year() -> None:
    today = date(2026, 1, 1)
    birthday = date(1990, 6, 15)
    occ, age = _next_occurrence(birthday, today)
    assert occ == date(2026, 6, 15)
    assert age == 36


def test_next_occurrence_already_passed_this_year_rolls_to_next_year() -> None:
    today = date(2026, 9, 3)
    birthday = date(1990, 1, 10)
    occ, age = _next_occurrence(birthday, today)
    assert occ == date(2027, 1, 10)
    assert age == 37


def test_next_occurrence_today_counts_as_next() -> None:
    today = date(2026, 9, 3)
    birthday = date(1990, 9, 3)
    occ, age = _next_occurrence(birthday, today)
    assert occ == today
    assert age == 36


def test_next_occurrence_feb_29_falls_back_to_mar_1_in_a_non_leap_year() -> None:
    today = date(2026, 1, 1)  # 2026 is not a leap year
    birthday = date(1992, 2, 29)
    occ, age = _next_occurrence(birthday, today)
    assert occ == date(2026, 3, 1)
    assert age == 34


@pytest.mark.asyncio
async def test_birthdays_page_redirects_to_login_when_anonymous(client: AsyncClient) -> None:
    resp = await client.get("/admin-tools/birthdays", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/admin-tools/login"


@pytest.mark.asyncio
async def test_birthdays_page_forbidden_for_organizer(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-bdays1@example.com", UserRole.organizer)
    await session.commit()
    await _login(client, org.id)

    resp = await client.get("/admin-tools/birthdays", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/admin-tools/login"


@pytest.mark.asyncio
async def test_birthdays_page_shows_today_upcoming_and_current_month_by_default(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-bdays2@example.com", UserRole.admin)
    today = date.today()
    today_user = await make_user(session, "runner-bday-today@example.com")
    today_user.birthday = today.replace(year=1990)

    soon_user = await make_user(session, "runner-bday-soon@example.com")
    soon_date = today + timedelta(days=3)
    try:
        soon_user.birthday = soon_date.replace(year=1991)
    except ValueError:
        soon_user.birthday = date(1991, 3, 1)

    far_month = (today.month % 12) + 1  # a month that isn't the current one
    far_user = await make_user(session, "runner-bday-far@example.com")
    far_user.birthday = date(1992, far_month, 12)

    guest = await make_user(session, "runner-bday-guest@example.com")
    guest.is_guest = True
    guest.birthday = today.replace(year=1993)

    await session.commit()
    await _login(client, admin.id)

    resp = await client.get("/admin-tools/birthdays")
    assert resp.status_code == 200
    body = resp.text
    # "Сегодня" and "Ближайшие 7 дней" are unaffected by month selection —
    # both always show on the default view.
    assert today_user.last_name in body
    assert soon_user.last_name in body
    # A different month's birthday must NOT show up until that month is picked.
    assert far_user.last_name not in body
    # A guest with a matching birthday must never show up anywhere on the page.
    assert guest.last_name not in body

    resp2 = await client.get("/admin-tools/birthdays", params={"month": far_month})
    assert resp2.status_code == 200
    body2 = resp2.text
    assert far_user.last_name in body2
    # Switching months must not lose the today/upcoming sections.
    assert today_user.last_name in body2


@pytest.mark.asyncio
async def test_birthdays_page_falls_back_to_current_month_for_bad_month_param(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-bdays3@example.com", UserRole.admin)
    await session.commit()
    await _login(client, admin.id)

    for bad in ("0", "13", "not-a-number"):
        resp = await client.get("/admin-tools/birthdays", params={"month": bad})
        assert resp.status_code == 200
        assert MONTH_NAMES[date.today().month - 1] in resp.text
