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


class SupportMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
