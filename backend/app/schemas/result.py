from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ManualResultRequest(BaseModel):
    distance_km: float = Field(gt=0)
    duration_seconds: int = Field(gt=0)
    start_time: datetime | None = None


class ResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attendance_record_id: int
    distance_km: float
    duration_seconds: int
    pace_seconds_per_km: float
    start_time: datetime | None
    source: str
    source_file: str | None
    track_points: list[Any] | None
    elevation_profile: list[Any] | None
    telemetry: dict[str, Any] | None
    finish_status: str
    status: str
