"""Post-moderation for the whole profile form — see ProfileEditRequest for the
full rationale. `User`'s own columns always hold the last *approved* state;
this module is the only thing allowed to write to them from an edit request.
"""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.city import City
from app.models.enums import ModerationStatus
from app.models.profile_edit_request import ProfileEditRequest
from app.models.user import User
from app.services.running_club_service import ensure_running_club
from app.services.support_service import create_staff_ticket

# Every field UserUpdate accepts except prior_experience, which is frozen
# after its first answer (see api.users.update_me) and so has nothing left to
# moderate on a later edit.
MODERATED_FIELDS = [
    "first_name",
    "last_name",
    "city_id",
    "city",
    "gender",
    "birthday",
    "phone",
    "running_club",
    "parent_first_name",
    "parent_last_name",
    "parent_phone",
]

# A brand new registration has no prior approved name to fall back on while
# its first submission is pending — these go on `User` instead so the NOT
# NULL columns are satisfied. Parenthesised so they can never collide with a
# real submitted name (see schemas.validators._NAME_RE — parentheses fail
# that charset, and this is written directly, bypassing that validator).
PLACEHOLDER_FIRST_NAME = "Участник"
PLACEHOLDER_LAST_NAME = "(на проверке)"


def is_awaiting_first_review(user: User) -> bool:
    """True for a registration whose very first name submission hasn't been
    approved yet — still showing the bootstrap placeholder, not a real name."""
    return user.first_name == PLACEHOLDER_FIRST_NAME and user.last_name == PLACEHOLDER_LAST_NAME


def _json_safe(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    return value


def _from_json(field: str, value: Any) -> Any:
    if field == "birthday" and value is not None:
        return date.fromisoformat(value)
    return value


async def pending_request_for(session: AsyncSession, user: User) -> ProfileEditRequest | None:
    result: ProfileEditRequest | None = await session.scalar(
        select(ProfileEditRequest).where(
            ProfileEditRequest.user_id == user.id,
            ProfileEditRequest.status == ModerationStatus.pending,
        )
    )
    return result


async def has_pending_review(session: AsyncSession, user: User) -> bool:
    return await pending_request_for(session, user) is not None


async def submit_for_review(
    session: AsyncSession, user: User, payload: dict[str, Any]
) -> ProfileEditRequest | None:
    """Diff `payload` (already-validated fields from UserUpdate) against the
    current *committed* values on `user` and stage whatever's actually
    different. Replaces any request of this user's still pending — the most
    recent save always reflects the runner's full current intent, not a merge
    of several partial edits. Returns the new pending request, or None if
    nothing in `payload` actually differed (in which case any previously
    pending request is cancelled too, since there's nothing left to review)."""
    changes: dict[str, Any] = {}
    for field in MODERATED_FIELDS:
        if field not in payload:
            continue
        new_value = payload[field]
        if new_value != getattr(user, field):
            changes[field] = _json_safe(new_value)

    existing = await pending_request_for(session, user)
    if existing is not None:
        await session.delete(existing)
        await session.flush()

    if not changes:
        return None

    request = ProfileEditRequest(user_id=user.id, changes=changes, status=ModerationStatus.pending)
    session.add(request)
    await session.flush()
    return request


async def approve(session: AsyncSession, request: ProfileEditRequest) -> None:
    """Apply the staged changes onto the user's real columns — same
    side-effects update_me already applies at save time (city name mirrors
    city_id; running_club gets canonicalised), just deferred to this moment."""
    user = request.user
    for field, raw_value in request.changes.items():
        setattr(user, field, _from_json(field, raw_value))
    if "city_id" in request.changes:
        city_id = request.changes["city_id"]
        city = await session.get(City, city_id) if city_id is not None else None
        user.city = city.name if city is not None else None
    if request.changes.get("running_club"):
        club = await ensure_running_club(session, user.running_club)
        if club is not None:
            user.running_club = club.title
    request.status = ModerationStatus.approved
    request.decided_at = datetime.now(UTC)
    await session.flush()


def _rejection_message(request: ProfileEditRequest, reason: str) -> str:
    reason = reason.strip()
    if is_awaiting_first_review(request.user):
        lines = ["Данные, указанные при регистрации, не прошли проверку."]
        if reason:
            lines += ["", f"Причина: {reason}"]
        lines += ["", "Зайдите в профиль и укажите настоящие имя и фамилию."]
    else:
        lines = ["Изменения в профиле не приняты, анкета осталась прежней."]
        if reason:
            lines += ["", f"Причина: {reason}"]
        lines += ["", "При желании отправьте изменения ещё раз."]
    return "\n".join(lines)


async def reject(
    session: AsyncSession, request: ProfileEditRequest, admin: User, reason: str
) -> None:
    """Discard the staged changes — `user`'s columns are never touched, so
    this is a plain revert. A rejected *first* submission leaves the
    placeholder name in place; the frontend reads that as "enter your real
    data" (see is_awaiting_first_review)."""
    request.status = ModerationStatus.rejected
    request.decided_at = datetime.now(UTC)
    if not request.user.is_guest:
        await create_staff_ticket(
            session,
            recipient=request.user,
            admin=admin,
            body=_rejection_message(request, reason),
        )
    await session.flush()
