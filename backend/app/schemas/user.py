from datetime import date

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
