from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import settings
from app.models.enums import FinishStatus, ModerationStatus, ResultSource


@dataclass
class ValidationOutcome:
    finish_status: FinishStatus
    moderation_status: ModerationStatus
    distance_km: float
    duration_seconds: int
    pace_seconds_per_km: float
    distance_ok: bool
    start_time_ok: bool


def _to_utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


def validate_result(
    *,
    distance_km: float,
    duration_seconds: int,
    target_distance_km: float,
    source: ResultSource,
    protocol_finish_status: FinishStatus,
    result_start_time: datetime | None = None,
    group_start_time: datetime | None = None,
) -> ValidationOutcome:
    """Compute the stored distance/pace and moderation status for a result.

    finish_status is never recomputed here — GPS reception around Cheboksary
    is unreliable enough that a short/odd measured distance doesn't mean the
    runner actually DNF'd. It's decided once, at CSV import (or manual
    match), and a Result upload always just mirrors that (`protocol_finish_status`)
    rather than overriding it.

    - File/URL: distance is trusted (stored as measured) only when it's within
      ±tolerance% of the group's target AND the recorded start time is within
      ±tolerance minutes of the group's reference start — auto-`approved`. If
      either check fails, the file's time is still kept, but the distance falls
      back to the group's own target_distance_km (pace is computed from that,
      not the measured distance) and the result goes to admin moderation
      (`pending`) rather than being trusted outright.
    - Manual entry: always `pending`; the entered distance is used as-is —
      there's no GPS measurement to distrust, the runner is asserting it directly.
    """
    tol = settings.result_distance_tolerance_pct / 100.0
    distance_ok = abs(distance_km - target_distance_km) <= target_distance_km * tol

    start_time_ok = False
    g_start = _to_utc_naive(group_start_time)
    r_start = _to_utc_naive(result_start_time)
    if g_start is not None and r_start is not None:
        delta_min = abs((r_start - g_start).total_seconds()) / 60.0
        start_time_ok = delta_min <= settings.result_start_time_tolerance_minutes

    if source == ResultSource.manual:
        moderation_status = ModerationStatus.pending
        final_distance_km = distance_km
    elif distance_ok and start_time_ok:
        moderation_status = ModerationStatus.approved
        final_distance_km = distance_km
    else:
        moderation_status = ModerationStatus.pending
        final_distance_km = target_distance_km

    pace_seconds_per_km = duration_seconds / final_distance_km if final_distance_km > 0 else 0.0

    return ValidationOutcome(
        finish_status=protocol_finish_status,
        moderation_status=moderation_status,
        distance_km=final_distance_km,
        duration_seconds=duration_seconds,
        pace_seconds_per_km=pace_seconds_per_km,
        distance_ok=distance_ok,
        start_time_ok=start_time_ok,
    )
