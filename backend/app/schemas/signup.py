from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SignupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    runner_id: int
    group_id: int
    event_id: int
    created_at: datetime


class SignupGroupSummary(BaseModel):
    group_id: int
    group_name: str


class GroupSignupState(BaseModel):
    signed_up: bool
    signup_id: int | None = None
    # Set when the runner is signed up for a *different* group of this same
    # event — the frontend offers to switch instead of just erroring out on
    # a plain sign-up attempt.
    other_group: SignupGroupSummary | None = None


class EventSignupState(BaseModel):
    signed_up: bool
    group_id: int | None = None
    group_name: str | None = None


class MySignupEntry(BaseModel):
    signup_id: int
    group_id: int
    group_name: str
    location: str
    event_id: int
    event_title: str
    event_date: date_type
    start_time: datetime | None


class AwaitingResultEntry(BaseModel):
    """A past event the runner signed up to, for which they can still self-report
    a result (or one is pending). Once approved it drops off — it's then in the
    protocol / their history."""

    # Null for an entry added via the "Я бегал(а)" deep link — no signup behind it.
    signup_id: int | None
    group_id: int
    group_name: str
    location: str
    event_id: int
    event_title: str
    event_date: date_type
    start_time: datetime | None
    # True when the group is settled and can't be switched from the upload
    # form (see _group_is_fixed): a record with no result yet, or a
    # pending/approved one. False for a *rejected* record too — that's the
    # "wrong group, please redo" case the switcher exists to fix.
    has_record: bool = False
    has_result: bool
    moderation_status: str | None  # 'pending' | 'approved' | 'rejected' | None


class SignupRosterEntry(BaseModel):
    signup_id: int
    runner_id: int
    display_name: str
    avatar: str | None


class SignupRoster(BaseModel):
    group_id: int
    count: int
    entries: list[SignupRosterEntry]
