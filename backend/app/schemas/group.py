from datetime import date as date_type
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GroupCreate(BaseModel):
    location: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    distance_code: str | None = Field(default=None, max_length=50)
    target_distance_km: float = Field(gt=0)
    pace_min: str | None = Field(default=None, max_length=20)
    pace_max: str | None = Field(default=None, max_length=20)
    start_time: datetime | None = None


class GroupUpdate(BaseModel):
    location: str | None = Field(default=None, min_length=1, max_length=255)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    distance_code: str | None = Field(default=None, max_length=50)
    target_distance_km: float | None = Field(default=None, gt=0)
    pace_min: str | None = Field(default=None, max_length=20)
    pace_max: str | None = Field(default=None, max_length=20)
    start_time: datetime | None = None


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    location: str
    name: str
    distance_code: str | None
    target_distance_km: float
    pace_min: str | None
    pace_max: str | None
    start_time: datetime | None
    route_gpx: str | None
    # Always the parent event's date (see combine_event_date_and_time) — lets
    # the frontend decide whether this group's event is past without a
    # second fetch, e.g. to hide the signup roster once it's happened.
    event_date: date_type
    signup_count: int
    counts_toward_rating: bool


class RouteMap(BaseModel):
    track_points: list[dict[str, Any]]
    elevation_profile: list[dict[str, Any]]
    distance_km: float


class ProtocolEntry(BaseModel):
    rank: int | None
    attendance_id: int
    runner_id: int | None
    display_name: str
    distance_km: float | None
    duration_seconds: int | None
    pace_seconds_per_km: float | None
    finish_status: str
    moderation_status: str | None


class Protocol(BaseModel):
    group_id: int
    # All group ids merged into this protocol (siblings sharing the same
    # event + distance_code) — just [group_id] when it has no family.
    group_ids: list[int]
    finishers: list[ProtocolEntry]
    pending: list[ProtocolEntry]
    dnf: list[ProtocolEntry]
