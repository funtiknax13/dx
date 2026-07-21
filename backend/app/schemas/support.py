from datetime import datetime

from pydantic import BaseModel, Field


class SupportMessageOut(BaseModel):
    id: int
    is_staff: bool
    body: str
    created_at: datetime


class SupportTicketOut(BaseModel):
    id: int
    status: str
    created_at: datetime
    preview: str
    has_unread: bool


class SupportTicketDetailOut(BaseModel):
    id: int
    status: str
    created_at: datetime
    messages: list[SupportMessageOut]


class SupportTicketCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    guest_name: str | None = Field(default=None, max_length=150)
    guest_contact: str | None = Field(default=None, max_length=255)


class SupportMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
