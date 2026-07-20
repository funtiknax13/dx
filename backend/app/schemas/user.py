from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import Gender, PriorExperience, UserRole


class UserMe(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    email: EmailStr
    role: UserRole
    email_verified: bool
    city: str | None = None
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
    city: str | None = Field(default=None, max_length=120)
    gender: Gender | None = None
    birthday: date | None = None
    phone: str | None = Field(default=None, max_length=40)
    running_club: str | None = Field(default=None, max_length=150)
    prior_experience: PriorExperience | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class ParticipationHistoryItem(BaseModel):
    attendance_id: int
    group_id: int
    group_name: str
    event_id: int
    event_title: str
    event_date: date
    finish_status: str
    has_result: bool


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
