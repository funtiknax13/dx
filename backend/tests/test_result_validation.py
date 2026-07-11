from datetime import UTC, datetime, timedelta

from app.models.enums import FinishStatus, ModerationStatus, ResultSource
from app.services.result_validation_service import compute_finish_status, validate_result

GROUP_START = datetime(2026, 5, 1, 8, 0, tzinfo=UTC)


def test_finished_when_distance_within_tolerance() -> None:
    assert compute_finish_status(9.1, 10.0) == FinishStatus.finished  # 9% short, tol 10%
    assert compute_finish_status(10.0, 10.0) == FinishStatus.finished


def test_dnf_when_distance_well_below_target() -> None:
    assert compute_finish_status(5.0, 10.0) == FinishStatus.dnf


def test_file_within_all_tolerances_is_approved_and_finished() -> None:
    outcome = validate_result(
        distance_km=10.2,
        target_distance_km=10.0,
        source=ResultSource.file,
        result_start_time=GROUP_START + timedelta(minutes=15),
        group_start_time=GROUP_START,
    )
    assert outcome.finish_status == FinishStatus.finished
    assert outcome.moderation_status == ModerationStatus.approved


def test_file_distance_mismatch_goes_pending() -> None:
    # Distance 30% over target -> outside ±10% approval band -> pending (but still finished).
    outcome = validate_result(
        distance_km=13.0,
        target_distance_km=10.0,
        source=ResultSource.file,
        result_start_time=GROUP_START,
        group_start_time=GROUP_START,
    )
    assert outcome.finish_status == FinishStatus.finished
    assert outcome.moderation_status == ModerationStatus.pending


def test_file_start_time_mismatch_goes_pending() -> None:
    outcome = validate_result(
        distance_km=10.0,
        target_distance_km=10.0,
        source=ResultSource.file,
        result_start_time=GROUP_START + timedelta(hours=3),
        group_start_time=GROUP_START,
    )
    assert outcome.moderation_status == ModerationStatus.pending


def test_file_distance_below_target_is_dnf_and_pending() -> None:
    outcome = validate_result(
        distance_km=4.0,
        target_distance_km=10.0,
        source=ResultSource.file,
        result_start_time=GROUP_START,
        group_start_time=GROUP_START,
    )
    assert outcome.finish_status == FinishStatus.dnf
    assert outcome.moderation_status == ModerationStatus.pending


def test_manual_entry_always_pending() -> None:
    outcome = validate_result(
        distance_km=10.0,
        target_distance_km=10.0,
        source=ResultSource.manual,
        result_start_time=GROUP_START,
        group_start_time=GROUP_START,
    )
    assert outcome.moderation_status == ModerationStatus.pending


def test_missing_start_time_prevents_approval() -> None:
    outcome = validate_result(
        distance_km=10.0,
        target_distance_km=10.0,
        source=ResultSource.file,
        result_start_time=None,
        group_start_time=GROUP_START,
    )
    assert outcome.moderation_status == ModerationStatus.pending
