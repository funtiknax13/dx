from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GuestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    avatar: str | None


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    guest_user_id: int
    claimant_user_id: int
    status: str
    created_at: datetime
    decided_at: datetime | None


class MyClaimOut(ClaimOut):
    guest: GuestOut
