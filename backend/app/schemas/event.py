# Alias the date type: a model field literally named `date` with a default would
# otherwise shadow the imported `date` symbol during class-body evaluation.
from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    date: date_type
    description: str | None = None


class EventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    date: date_type | None = None
    description: str | None = None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    date: date_type
    description: str | None
    cover_image: str | None
    created_by: int
    created_at: datetime


class EventPhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    image: str
    thumbnail: str | None
    uploaded_by: int | None
    created_at: datetime
