from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SignupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    runner_id: int
    group_id: int
    created_at: datetime


class GroupSignupState(BaseModel):
    signed_up: bool
    signup_id: int | None = None


class SignupRosterEntry(BaseModel):
    signup_id: int
    runner_id: int
    display_name: str
    avatar: str | None


class SignupRoster(BaseModel):
    group_id: int
    count: int
    entries: list[SignupRosterEntry]
