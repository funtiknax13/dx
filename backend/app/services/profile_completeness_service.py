from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.profile_review_service import has_pending_review
from app.services.survey_service import stats_locked_pending_survey

# Runners younger than this must supply guardian contacts (см. задача 8).
MINOR_AGE = 14
PARENT_FIELDS = ["parent_first_name", "parent_last_name", "parent_phone"]


def age_years(birthday: date, today: date | None = None) -> int:
    today = today or date.today()
    return today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))


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
    # Under-14 runners additionally need a parent's name and phone. Only checked
    # once the birthday is known (birthday itself is already gated above).
    if user.birthday is not None and age_years(user.birthday) < MINOR_AGE:
        missing += [f for f in PARENT_FIELDS if getattr(user, f) is None]
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
    never having run with us before, from registration until they've both
    run their first DX *and* completed the newbie survey — see
    survey_service.stats_locked_pending_survey (they stay locked even before
    their first tracked attendance; there's simply nothing to show them on
    the survey page yet — see survey_service.survey_required_for, used by
    GET /surveys/active). "profile_pending_review" for a runner with a
    profile edit (or the whole account, for a fresh/backfilled registration)
    still awaiting moderation — see profile_review_service; their *approved*
    data may well satisfy every field below, this is a separate gate on top.
    missing_fields is only ever populated for "profile_incomplete"."""
    if viewer is None:
        return "anonymous", []
    completeness = check(viewer)
    if not completeness.is_complete:
        return "profile_incomplete", completeness.missing_fields
    if await has_pending_review(session, viewer):
        return "profile_pending_review", []
    if await stats_locked_pending_survey(session, viewer):
        return "survey_required", []
    return None, []
