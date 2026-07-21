from datetime import UTC, datetime, timedelta

from app.models.enums import FinishStatus, ModerationStatus, ResultSource
from app.services.result_validation_service import validate_result

GROUP_START = datetime(2026, 5, 1, 8, 0, tzinfo=UTC)


def test_file_within_all_tolerances_uses_measured_distance_and_approves() -> None:
    outcome = validate_result(
        distance_km=10.2,
        duration_seconds=3600,
        target_distance_km=10.0,
        source=ResultSource.file,
        protocol_finish_status=FinishStatus.finished,
        result_start_time=GROUP_START + timedelta(minutes=15),
        group_start_time=GROUP_START,
    )
    assert outcome.moderation_status == ModerationStatus.approved
    assert outcome.distance_km == 10.2
    assert outcome.pace_seconds_per_km == 3600 / 10.2
    assert outcome.finish_status == FinishStatus.finished


def test_file_distance_mismatch_falls_back_to_group_target_and_goes_pending() -> None:
    # GPS said 13km against a 10km target — outside ±10% band. Don't trust the
    # measured distance (unreliable GPS reception, see result_validation_service
    # docstring); fall back to the group's own reference distance instead.
    outcome = validate_result(
        distance_km=13.0,
        duration_seconds=3600,
        target_distance_km=10.0,
        source=ResultSource.file,
        protocol_finish_status=FinishStatus.finished,
        result_start_time=GROUP_START,
        group_start_time=GROUP_START,
    )
    assert outcome.moderation_status == ModerationStatus.pending
    assert outcome.distance_km == 10.0
    assert outcome.pace_seconds_per_km == 3600 / 10.0
    assert outcome.duration_seconds == 3600


def test_file_start_time_mismatch_falls_back_to_group_target_and_goes_pending() -> None:
    # Distance matched fine, but the recorded start time is way off (e.g. a
    # stale/wrong export) — still don't trust the measured distance.
    outcome = validate_result(
        distance_km=10.0,
        duration_seconds=3600,
        target_distance_km=10.0,
        source=ResultSource.file,
        protocol_finish_status=FinishStatus.finished,
        result_start_time=GROUP_START + timedelta(hours=3),
        group_start_time=GROUP_START,
    )
    assert outcome.moderation_status == ModerationStatus.pending
    # Coincidentally equal to the measured value here, but arrived at via the
    # target-distance fallback, not by trusting the measurement.
    assert outcome.distance_km == 10.0


def test_file_short_distance_still_pending_but_finish_status_untouched() -> None:
    """The actual bug report this guards against: a short/odd GPS reading
    (Cheboksary reception issues) must never flip a protocol-finished runner
    to DNF — it only routes the result to moderation."""
    outcome = validate_result(
        distance_km=4.0,
        duration_seconds=3600,
        target_distance_km=10.0,
        source=ResultSource.file,
        protocol_finish_status=FinishStatus.finished,
        result_start_time=GROUP_START,
        group_start_time=GROUP_START,
    )
    assert outcome.moderation_status == ModerationStatus.pending
    assert outcome.distance_km == 10.0
    assert outcome.finish_status == FinishStatus.finished


def test_finish_status_always_mirrors_protocol_never_computed_from_distance() -> None:
    # Even a well-matched file result on a protocol-DNF record stays DNF.
    outcome = validate_result(
        distance_km=10.0,
        duration_seconds=3600,
        target_distance_km=10.0,
        source=ResultSource.file,
        protocol_finish_status=FinishStatus.dnf,
        result_start_time=GROUP_START,
        group_start_time=GROUP_START,
    )
    assert outcome.finish_status == FinishStatus.dnf
    assert outcome.moderation_status == ModerationStatus.approved


def test_manual_entry_always_pending_and_keeps_entered_distance() -> None:
    outcome = validate_result(
        distance_km=10.0,
        duration_seconds=3600,
        target_distance_km=10.0,
        source=ResultSource.manual,
        protocol_finish_status=FinishStatus.finished,
        result_start_time=GROUP_START,
        group_start_time=GROUP_START,
    )
    assert outcome.moderation_status == ModerationStatus.pending
    assert outcome.distance_km == 10.0


def test_missing_start_time_prevents_approval() -> None:
    outcome = validate_result(
        distance_km=10.0,
        duration_seconds=3600,
        target_distance_km=10.0,
        source=ResultSource.file,
        protocol_finish_status=FinishStatus.finished,
        result_start_time=None,
        group_start_time=GROUP_START,
    )
    assert outcome.moderation_status == ModerationStatus.pending
    assert outcome.distance_km == 10.0
