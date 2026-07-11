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
