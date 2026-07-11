import pytest

from app.services.gpx_service import TrackParseError, parse_gpx

SAMPLE_GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>Test</name><trkseg>
    <trkpt lat="55.7500" lon="37.6200"><ele>150.0</ele><time>2026-05-01T08:00:00Z</time></trkpt>
    <trkpt lat="55.7510" lon="37.6210"><ele>152.0</ele><time>2026-05-01T08:05:00Z</time></trkpt>
    <trkpt lat="55.7520" lon="37.6220"><ele>151.0</ele><time>2026-05-01T08:10:00Z</time></trkpt>
  </trkseg></trk>
</gpx>
"""


def test_parse_gpx_extracts_points_and_duration() -> None:
    parsed = parse_gpx(SAMPLE_GPX)
    assert len(parsed.track_points) == 3
    assert parsed.track_points[0]["lat"] == pytest.approx(55.75, abs=1e-4)
    assert parsed.duration_seconds == 600  # 10 minutes
    assert parsed.start_time is not None
    assert parsed.distance_km > 0
    assert len(parsed.elevation_profile) == 3
    assert parsed.elevation_profile[0]["distance_km"] == 0.0
    assert parsed.pace_seconds_per_km > 0


def test_parse_gpx_accepts_bytes() -> None:
    parsed = parse_gpx(SAMPLE_GPX.encode("utf-8"))
    assert len(parsed.track_points) == 3


def test_parse_gpx_invalid_raises() -> None:
    with pytest.raises(TrackParseError):
        parse_gpx("not a gpx file at all")


def test_parse_gpx_empty_track_raises() -> None:
    empty = (
        '<?xml version="1.0"?><gpx version="1.1" '
        'xmlns="http://www.topografix.com/GPX/1/1"></gpx>'
    )
    with pytest.raises(TrackParseError):
        parse_gpx(empty)
