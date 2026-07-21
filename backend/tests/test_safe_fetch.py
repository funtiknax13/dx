import pytest

from app.services.safe_fetch import FetchError, _validate_url, detect_workout_format


def test_rejects_non_https_scheme() -> None:
    with pytest.raises(FetchError, match="https"):
        _validate_url("http://example.com/export.gpx")


def test_rejects_loopback_literal() -> None:
    with pytest.raises(FetchError, match="disallowed"):
        _validate_url("https://127.0.0.1/export.gpx")


def test_rejects_loopback_hostname() -> None:
    with pytest.raises(FetchError, match="disallowed"):
        _validate_url("https://localhost/export.gpx")


def test_rejects_private_range_literal() -> None:
    with pytest.raises(FetchError, match="disallowed"):
        _validate_url("https://10.0.0.5/export.gpx")


def test_rejects_link_local_cloud_metadata_address() -> None:
    with pytest.raises(FetchError, match="disallowed"):
        _validate_url("https://169.254.169.254/latest/meta-data/")


def test_accepts_a_plausible_public_https_url() -> None:
    # example.com is IANA-reserved for exactly this (a stable, always-public
    # domain) — this only exercises hostname resolution/validation, no actual
    # HTTP request is made here.
    _validate_url("https://example.com/export.gpx")


def test_detect_workout_format_from_content_type() -> None:
    assert detect_workout_format(b"", "application/gpx+xml", "") == "gpx"
    assert detect_workout_format(b"", "application/vnd.ant.fit", "") == "fit"


def test_detect_workout_format_from_content_disposition() -> None:
    assert detect_workout_format(b"", "", 'attachment; filename="run.gpx"') == "gpx"
    assert detect_workout_format(b"", "", 'attachment; filename="run.fit"') == "fit"


def test_detect_workout_format_sniffs_gpx_content() -> None:
    body = b'<?xml version="1.0"?><gpx></gpx>'
    assert detect_workout_format(body, "application/octet-stream", "") == "gpx"


def test_detect_workout_format_sniffs_fit_content() -> None:
    body = b"\x0e\x10\xd9\x07" + b"\x00" * 4 + b".FIT" + b"\x00" * 20
    assert detect_workout_format(body, "application/octet-stream", "") == "fit"


def test_detect_workout_format_unrecognized_returns_none() -> None:
    assert detect_workout_format(b"not a track file", "text/plain", "") is None
