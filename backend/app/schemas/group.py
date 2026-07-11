from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GroupCreate(BaseModel):
    location: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    target_distance_km: float = Field(gt=0)
    pace_min: str | None = Field(default=None, max_length=20)
    pace_max: str | None = Field(default=None, max_length=20)
    start_time: datetime | None = None


class GroupUpdate(BaseModel):
    location: str | None = Field(default=None, min_length=1, max_length=255)
    name: str | None = Field(default=None, min_length=1, max_length=255)
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
    target_distance_km: float
    pace_min: str | None
    pace_max: str | None
    start_time: datetime | None
    route_gpx: str | None


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
    finishers: list[ProtocolEntry]
    pending: list[ProtocolEntry]
    dnf: list[ProtocolEntry]
