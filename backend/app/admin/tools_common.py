"""Shared plumbing for the /admin-tools mini-app (organizer + admin surface).

Distinct from SQLAdmin's own auth (`app.admin.auth`, admin-role only): admin-tools
is reachable by both `organizer` and `admin`, with per-resource ownership checks
(an organizer only manages their own events/groups; admin manages everything).
Both share the same session cookie (see SessionMiddleware in app.main), so an admin
who reaches admin-tools via SSO is automatically also authenticated into SQLAdmin.
"""

from datetime import date as date_type
from datetime import datetime
from datetime import time as time_type
from pathlib import Path

from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.requests import Request

from app.core.db import SessionLocal
from app.core.security import verify_password
from app.models.enums import UserRole
from app.models.event import Event
from app.models.user import User

SESSION_KEY = "admin_user_id"

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def login_redirect() -> RedirectResponse:
    return RedirectResponse("/admin-tools/login", status_code=302)


def can_manage_event(user: User, event: Event) -> bool:
    """Admin manages every event; an organizer only their own."""
    return user.role == UserRole.admin or event.created_by == user.id


def combine_event_date_and_time(event_date: date_type, time_str: str) -> datetime | None:
    """A group's start_time always falls on its event's date — the form only
    collects time-of-day (see group_form.html), so the date always comes from
    here, never from user input."""
    if not time_str:
        return None
    return datetime.combine(event_date, time_type.fromisoformat(time_str))


async def get_tools_user(request: Request) -> User | None:
    """Return the logged-in User if their session is valid and their role is
    organizer or admin, else None."""
    user_id = request.session.get(SESSION_KEY)
    if not user_id:
        return None
    async with SessionLocal() as session:
        user = await session.get(User, int(user_id))
    if user is None or user.role not in (UserRole.organizer, UserRole.admin):
        return None
    return user


async def verify_tools_credentials(email: str, password: str) -> User | None:
    """Fallback login (email/password) for reaching admin-tools directly, without
    coming from the frontend via SSO — e.g. a bookmarked link after the SPA session
    expired. Accepts organizer or admin accounts."""
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
    if user is None or user.role not in (UserRole.organizer, UserRole.admin):
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
