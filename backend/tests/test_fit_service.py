import struct

import pytest

from app.services.fit_service import parse_fit
from app.services.gpx_service import TrackParseError

# FIT epoch: seconds between the Unix epoch and 1989-12-31 00:00:00 UTC.
_FIT_EPOCH = 631065600
_DEG_TO_SEMICIRCLES = (2**31) / 180.0


def _semicircles(deg: float) -> int:
    return int(deg * _DEG_TO_SEMICIRCLES)


def _build_minimal_fit() -> bytes:
    """Synthesize a minimal valid FIT file with three 'record' messages.

    One definition message (global num 20) followed by three data messages carrying
    timestamp, position, distance, altitude and heart rate. Base types are little-endian.
    """
    # Definition message for local type 0.
    # fields: (field_def_num, size, base_type)
    fields = [
        (253, 4, 0x86),  # timestamp   uint32
        (0, 4, 0x85),    # position_lat sint32
        (1, 4, 0x85),    # position_long sint32
        (5, 4, 0x86),    # distance     uint32 (scale 100 -> meters)
        (2, 2, 0x84),    # altitude     uint16 (scale 5, offset 500)
        (3, 1, 0x02),    # heart_rate   uint8
    ]
    definition = bytearray()
    definition.append(0x40)  # definition message, local type 0
    definition.append(0x00)  # reserved
    definition.append(0x00)  # architecture: little-endian
    definition += struct.pack("<H", 20)  # global message number: record
    definition.append(len(fields))
    for fdn, size, base in fields:
        definition += bytes([fdn, size, base])

    def altitude_raw(m: float) -> int:
        return int((m + 500) * 5)

    rows = [
        (0, 55.75, 37.62, 0.0, 150.0, 120),
        (120, 55.76, 37.63, 500.0, 152.0, 140),
        (240, 55.77, 37.64, 1000.0, 151.0, 150),
    ]
    data = bytearray()
    for secs, lat, lon, dist_m, alt_m, hr in rows:
        data.append(0x00)  # data message, local type 0
        data += struct.pack("<I", _FIT_EPOCH + secs)
        data += struct.pack("<i", _semicircles(lat))
        data += struct.pack("<i", _semicircles(lon))
        data += struct.pack("<I", int(dist_m * 100))
        data += struct.pack("<H", altitude_raw(alt_m))
        data += struct.pack("<B", hr)

    body = bytes(definition) + bytes(data)

    header = bytearray()
    header.append(14)  # header size
    header.append(0x10)  # protocol version
    header += struct.pack("<H", 2100)  # profile version
    header += struct.pack("<I", len(body))  # data size
    header += b".FIT"
    header += struct.pack("<H", 0)  # header CRC (ignored, check_crc=False)

    return bytes(header) + body + struct.pack("<H", 0)  # trailing file CRC (ignored)


def test_parse_fit_extracts_track_distance_and_telemetry() -> None:
    parsed = parse_fit(_build_minimal_fit())
    assert len(parsed.track_points) == 3
    assert parsed.track_points[0]["lat"] == pytest.approx(55.75, abs=1e-3)
    assert parsed.distance_km == pytest.approx(1.0, abs=1e-3)
    assert parsed.duration_seconds == 240
    assert parsed.start_time is not None
    assert parsed.telemetry is not None
    assert parsed.telemetry["heart_rate"]["max"] == 150
    assert len(parsed.elevation_profile) == 3


def test_parse_fit_invalid_raises() -> None:
    with pytest.raises(TrackParseError):
        parse_fit(b"this is definitely not a fit file")
