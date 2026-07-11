from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import settings
from app.models.enums import FinishStatus, ModerationStatus, ResultSource


@dataclass
class ValidationOutcome:
    finish_status: FinishStatus
    moderation_status: ModerationStatus
    distance_ok: bool
    start_time_ok: bool


def _to_utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


def compute_finish_status(distance_km: float, target_distance_km: float) -> FinishStatus:
    """finished when distance >= target * (1 - tolerance); otherwise DNF.

    One-sided: only a shortfall below target demotes to DNF (per CLAUDE.md)."""
    tol = settings.result_distance_tolerance_pct / 100.0
    threshold = target_distance_km * (1 - tol)
    return FinishStatus.finished if distance_km >= threshold else FinishStatus.dnf


def validate_result(
    *,
    distance_km: float,
    target_distance_km: float,
    source: ResultSource,
    result_start_time: datetime | None = None,
    group_start_time: datetime | None = None,
) -> ValidationOutcome:
    """Compute finish status and moderation status for a result.

    - finish_status: distance vs target with distance tolerance (see compute_finish_status).
    - moderation status: manual entry is always `pending`. File uploads are `approved`
      only when BOTH the distance is within ±tolerance% of target AND the start time is
      within ±tolerance minutes of the group's reference start time; otherwise `pending`.
    """
    finish_status = compute_finish_status(distance_km, target_distance_km)

    tol = settings.result_distance_tolerance_pct / 100.0
    # Two-sided distance check for approval (over- and under-shoot both suspicious).
    distance_ok = abs(distance_km - target_distance_km) <= target_distance_km * tol

    start_time_ok = False
    g_start = _to_utc_naive(group_start_time)
    r_start = _to_utc_naive(result_start_time)
    if g_start is not None and r_start is not None:
        delta_min = abs((r_start - g_start).total_seconds()) / 60.0
        start_time_ok = delta_min <= settings.result_start_time_tolerance_minutes

    if source == ResultSource.manual:
        moderation_status = ModerationStatus.pending
    elif distance_ok and start_time_ok:
        moderation_status = ModerationStatus.approved
    else:
        moderation_status = ModerationStatus.pending

    return ValidationOutcome(
        finish_status=finish_status,
        moderation_status=moderation_status,
        distance_ok=distance_ok,
        start_time_ok=start_time_ok,
    )
