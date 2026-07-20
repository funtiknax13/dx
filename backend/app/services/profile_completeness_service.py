from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.survey_service import survey_required_for

# Fields that gate access to community stats/rating (see CLAUDE.md discussion
# on the "100% profile" motivation mechanic) — first/last name and email are
# already mandatory at registration, so they're not listed here; they're
# always satisfied. Order is the order shown in the completion checklist.
GATED_FIELDS: list[str] = [
    "birthday",
    "avatar",
    "city",
    "gender",
    "phone",
    "running_club",
    "prior_experience",
]


@dataclass
class ProfileCompleteness:
    is_complete: bool
    missing_fields: list[str]


def check(user: User) -> ProfileCompleteness:
    """Which gated fields are still unanswered. `running_club` treats ""
    (the "not in a club" checkbox) as answered — only None means the runner
    has never touched the field at all. Email verification isn't a profile
    field but gates the same way, so it's folded into the same missing list
    under the "email_verified" key."""
    missing = [f for f in GATED_FIELDS if getattr(user, f) is None]
    if not user.email_verified:
        missing.append("email_verified")
    return ProfileCompleteness(is_complete=not missing, missing_fields=missing)


async def stats_access_lock(
    session: AsyncSession, viewer: User | None
) -> tuple[str | None, list[str]]:
    """(lock_reason, missing_fields) gating the community rating/leaderboard
    and other runners' stats — None reason means unlocked. "anonymous" for a
    logged-out visitor (told to register *and* complete their profile);
    "profile_incomplete" for a logged-in runner who hasn't finished theirs
    (told just to finish it); "survey_required" for a runner who reported
    never having run with us before and has since logged their first
    tracked attendance — see survey_service.survey_required_for. missing_fields
    is only ever populated for "profile_incomplete"; the frontend fetches the
    actual survey separately (GET /surveys/active) when it sees
    "survey_required"."""
    if viewer is None:
        return "anonymous", []
    completeness = check(viewer)
    if not completeness.is_complete:
        return "profile_incomplete", completeness.missing_fields
    if await survey_required_for(session, viewer) is not None:
        return "survey_required", []
    return None, []
