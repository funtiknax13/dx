import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import Gender, PriorExperience, UserRole


def normalize_ru_phone(value: str | None) -> str | None:
    """Reduce any RU phone input to canonical +7XXXXXXXXXX, or None if empty.
    Accepts 8XXXXXXXXXX, +7XXXXXXXXXX, or a bare 10-digit national number."""
    if value is None:
        return None
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    if len(digits) == 11 and digits[0] in "78":
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError("Телефон должен быть российским: +7 и 10 цифр")
    return f"+7{digits}"


def validate_birthday(value: date | None) -> date | None:
    if value is None:
        return None
    if value > date.today():
        raise ValueError("Дата рождения не может быть в будущем")
    if value.year < 1900:
        raise ValueError("Проверьте год рождения")
    return value


class UserMe(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    email: EmailStr
    role: UserRole
    email_verified: bool
    city: str | None = None
    city_id: int | None = None
    gender: Gender | None = None
    birthday: date | None = None
    phone: str | None = None
    avatar: str | None = None
    # "" means "not in a club" (explicitly answered); None means untouched —
    # see profile_completeness_service.
    running_club: str | None = None
    prior_experience: PriorExperience | None = None


class UserUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    # Picked from the canonical list; the server mirrors the chosen city's name
    # into `city` for display. `city` is still accepted for legacy/free-text.
    city_id: int | None = None
    city: str | None = Field(default=None, max_length=120)
    gender: Gender | None = None
    birthday: date | None = None
    phone: str | None = Field(default=None, max_length=40)
    running_club: str | None = Field(default=None, max_length=150)
    prior_experience: PriorExperience | None = None

    @field_validator("phone")
    @classmethod
    def _norm_phone(cls, v: str | None) -> str | None:
        return normalize_ru_phone(v)

    @field_validator("birthday")
    @classmethod
    def _check_birthday(cls, v: date | None) -> date | None:
        return validate_birthday(v)


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class AccessLockOut(BaseModel):
    """The current user's completeness gate (see profile_completeness_service).
    None reason = unlocked; "profile_incomplete" / "survey_required" otherwise."""

    lock_reason: str | None
    missing_fields: list[str]


class ParticipationHistoryItem(BaseModel):
    attendance_id: int
    group_id: int
    group_name: str
    event_id: int
    event_title: str
    event_date: date
    finish_status: str
    has_result: bool
    # pending / approved / rejected / None — lets the owner's view know whether a
    # rejected result can be re-uploaded (see ParticipationHistory on the frontend).
    moderation_status: str | None = None


class AchievementItem(BaseModel):
    threshold: int
    reached: bool
    reached_at: date | None = None
    event_id: int | None = None
    event_title: str | None = None


class PublicProfile(BaseModel):
    id: int
    first_name: str
    last_name: str
    avatar: str | None = None
    is_guest: bool
    # Null for guest profiles — a guest was never registered by anyone, its
    # created_at is just whenever a CSV import happened to conjure it up
    # (often *after* the run it records), not a meaningful "joined on" date.
    registered_at: datetime | None = None
    # "rating" = count of finished attendances in groups that count toward the
    # rating (i.e. "full DX" — see app.services.stats_service) — kept under its
    # original name since RatingPage already depends on this exact number.
    # All None together when `lock_reason` is set — a viewer who hasn't
    # registered/finished their own profile can't see anyone else's stats
    # (see profile_completeness_service.stats_access_lock); looking at your
    # own profile is never locked.
    rating: int | None = None
    first_run_date: date | None = None
    total_runs_count: int | None = None
    full_dx_km: float | None = None
    km_this_month: float | None = None
    current_streak: int | None = None
    longest_streak: int | None = None
    achievements: list[AchievementItem] | None = None
    lock_reason: str | None = None
    missing_fields: list[str] = []
    # Not embedded here — paginated separately via GET /users/{id}/history,
    # since an active runner's full history can run into the hundreds.


class AccountExportHistoryItem(BaseModel):
    attendance_id: int
    group_id: int
    group_name: str
    event_id: int
    event_title: str
    event_date: date
    finish_status: str
    distance_km: float | None = None
    duration_seconds: int | None = None
    pace_seconds_per_km: float | None = None
    moderation_status: str | None = None


class AccountExportSignup(BaseModel):
    signup_id: int
    group_id: int
    group_name: str
    event_id: int
    event_title: str
    event_date: date


class AccountExport(BaseModel):
    """Everything the platform holds about one runner, for the self-service
    "download my data" right under 152-FZ art. 14."""

    profile: UserMe
    account_created_at: datetime
    privacy_accepted_at: datetime | None
    history: list[AccountExportHistoryItem]
    signups: list[AccountExportSignup]


class AccountDeleteRequest(BaseModel):
    password: str
