from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import Gender, UserRole


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


class UserUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    city: str | None = Field(default=None, max_length=120)
    gender: Gender | None = None
    birthday: date | None = None
    phone: str | None = Field(default=None, max_length=40)


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


class PublicProfile(BaseModel):
    id: int
    first_name: str
    last_name: str
    avatar: str | None = None
    rating: int
    history: list[ParticipationHistoryItem]


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
