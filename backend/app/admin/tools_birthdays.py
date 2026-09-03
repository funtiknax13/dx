from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.admin.tools_common import get_tools_user, login_redirect, templates
from app.core.db import SessionLocal
from app.models.enums import UserRole
from app.models.user import User

router = APIRouter(prefix="/admin-tools", tags=["admin-birthdays"], include_in_schema=False)

MONTH_NAMES = [
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
]


async def _require_admin(request: Request) -> User | None:
    """Birthdate is private profile data (never shown on the public profile —
    see the runner-facing frontend), so this stays a hard admin check like
    tools_runners.py's full-profile lookup, not a delegable StaffPermission."""
    user = await get_tools_user(request)
    if user is None or user.role != UserRole.admin:
        return None
    return user


@dataclass
class BirthdayRow:
    user: User
    birthday: date
    next_occurrence: date
    age: int
    days_until: int


def _next_occurrence(birthday: date, today: date) -> tuple[date, int]:
    """The next date this birthday falls on (today counts as "next"), and the
    age turned that day. Feb 29 in a non-leap year lands on Mar 1, same
    convention as most calendar apps."""
    try:
        this_year = birthday.replace(year=today.year)
    except ValueError:
        this_year = date(today.year, 3, 1)
    if this_year >= today:
        next_occ = this_year
    else:
        try:
            next_occ = birthday.replace(year=today.year + 1)
        except ValueError:
            next_occ = date(today.year + 1, 3, 1)
    return next_occ, next_occ.year - birthday.year


@router.get("/birthdays", response_class=HTMLResponse, response_model=None)
async def birthdays_page(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()

    today = date.today()
    async with SessionLocal() as session:
        users = list(
            await session.scalars(
                select(User)
                .where(User.is_guest.is_(False), User.birthday.is_not(None))
                .order_by(User.birthday)
            )
        )

    rows = []
    for u in users:
        birthday = u.birthday
        assert birthday is not None  # filtered by the query above
        next_occ, age = _next_occurrence(birthday, today)
        rows.append(
            BirthdayRow(
                user=u,
                birthday=birthday,
                next_occurrence=next_occ,
                age=age,
                days_until=(next_occ - today).days,
            )
        )

    today_rows = sorted(
        (r for r in rows if r.days_until == 0),
        key=lambda r: (r.user.last_name, r.user.first_name),
    )
    upcoming_rows = sorted((r for r in rows if 1 <= r.days_until <= 7), key=lambda r: r.days_until)

    months = [
        {
            "index": m,
            "name": MONTH_NAMES[m - 1],
            "rows": sorted(
                (r for r in rows if r.birthday.month == m), key=lambda r: r.birthday.day
            ),
        }
        for m in range(1, 13)
    ]

    return templates.TemplateResponse(
        request,
        "birthdays.html",
        {
            "active": "birthdays",
            "tools_user": user,
            "today_rows": today_rows,
            "upcoming_rows": upcoming_rows,
            "months": months,
            "total": len(rows),
            "current_month": today.month,
        },
    )
