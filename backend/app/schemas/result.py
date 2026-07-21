from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ManualResultRequest(BaseModel):
    distance_km: float = Field(gt=0)
    duration_seconds: int = Field(gt=0)
    start_time: datetime | None = None


class ImportUrlRequest(BaseModel):
    # Left as a plain string, not pydantic's Url type — safe_fetch does its own
    # scheme/host validation (https-only, private-IP checks) and gives a
    # clearer error message than a generic URL-format failure would.
    url: str = Field(min_length=1, max_length=2000)


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
