from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ParsedTrack:
    """Normalized output of GPX/FIT parsing, shared by both services."""

    distance_km: float
    duration_seconds: int
    start_time: datetime | None = None
    track_points: list[dict[str, Any]] = field(default_factory=list)
    elevation_profile: list[dict[str, Any]] = field(default_factory=list)
    telemetry: dict[str, Any] | None = None

    @property
    def pace_seconds_per_km(self) -> float:
        if self.distance_km <= 0:
            return 0.0
        return self.duration_seconds / self.distance_km
