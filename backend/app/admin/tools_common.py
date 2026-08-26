"""Shared plumbing for the /admin-tools mini-app (organizer + admin surface).

Distinct from SQLAdmin's own auth (`app.admin.auth`, admin-role only): admin-tools
is reachable by both `organizer` and `admin`, with per-resource ownership checks
(an organizer only manages their own events/groups; admin manages everything).
Both share the same session cookie (see SessionMiddleware in app.main), so an admin
who reaches admin-tools via SSO is automatically also authenticated into SQLAdmin.
"""

from datetime import UTC, datetime
from datetime import date as date_type
from datetime import time as time_type
from pathlib import Path

from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.requests import Request

from app.core.db import SessionLocal
from app.core.security import verify_password
from app.core.timezone import EVENT_TZ
from app.models.enums import StaffPermission, UserRole
from app.models.event import Event
from app.models.user import User
from app.services.permissions_service import permissions_for

SESSION_KEY = "admin_user_id"

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
# Stored datetimes are UTC-aware (see combine_event_date_and_time); every admin
# view must render them as Cheboksary wall-clock time (see EVENT_TZ), never UTC
# or the viewer's own zone.
templates.env.filters["local_time"] = lambda dt: (
    dt.astimezone(EVENT_TZ).strftime("%H:%M") if dt else ""
)
templates.env.filters["local_date"] = lambda dt: (
    dt.astimezone(EVENT_TZ).strftime("%d.%m.%Y") if dt else ""
)
templates.env.filters["local_dt"] = lambda dt: (
    dt.astimezone(EVENT_TZ).strftime("%d.%m.%Y %H:%M") if dt else ""
)


def login_redirect() -> RedirectResponse:
    return RedirectResponse("/admin-tools/login", status_code=302)


def can_manage_event(user: User, event: Event) -> bool:
    """Admin manages every event; an organizer only their own."""
    return user.role == UserRole.admin or event.created_by == user.id


def combine_event_date_and_time(event_date: date_type, time_str: str) -> datetime | None:
    """A group's start_time always falls on its event's date — the form only
    collects time-of-day (see group_form.html), so the date always comes from
    here, never from user input. The time is entered as Cheboksary local time
    and converted to a real UTC instant for storage, so it round-trips to the
    same wall-clock number for every viewer (see EVENT_TZ) and still compares
    correctly against GPX/FIT-recorded (genuinely UTC) result times."""
    if not time_str:
        return None
    local = datetime.combine(event_date, time_type.fromisoformat(time_str), tzinfo=EVENT_TZ)
    return local.astimezone(UTC)


async def get_tools_user(request: Request) -> User | None:
    """Return the logged-in User if their session is valid and their role is
    organizer or admin, else None. Always attaches `granted_permissions` — a
    plain (non-mapped) attribute holding the set of StaffPermission this user
    currently holds: every value for admin (no query needed), only what's
    been explicitly granted for an organizer (see OrganizerPermission /
    permissions_service) — so both templates (nav/dashboard) and route
    guards (require_permission, below) share one source of truth without
    re-querying."""
    user_id = request.session.get(SESSION_KEY)
    if not user_id:
        return None
    async with SessionLocal() as session:
        user = await session.get(User, int(user_id))
        if user is None or user.role not in (UserRole.organizer, UserRole.admin):
            return None
        user.granted_permissions = await permissions_for(session, user)
    return user


async def require_permission(request: Request, permission: StaffPermission) -> User | None:
    """Like get_tools_user, but additionally requires this specific
    admin-tools permission — the flexible replacement for a page that used
    to be a flat `role == admin` check. Granting/revoking permissions is
    itself never delegable — see admin.tools_permissions, which stays a
    hard admin check regardless of what's been granted."""
    user = await get_tools_user(request)
    if user is None or permission not in user.granted_permissions:
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
