from typing import Any

from fitparse import FitFile

from app.services.gpx_service import TrackParseError
from app.services.track_types import ParsedTrack

# FIT stores lat/long as semicircles; convert to degrees.
_SEMICIRCLE_TO_DEG = 180.0 / (2**31)


def parse_fit(content: bytes) -> ParsedTrack:
    """Parse a FIT file into a normalized ParsedTrack, extracting track points,
    elevation, and telemetry (heart rate / cadence / power) when present."""
    try:
        # check_crc=False: tolerate exports from apps that write an incorrect trailing
        # CRC; the record data itself is still parsed and validated structurally.
        fit = FitFile(content, check_crc=False)
        records = list(fit.get_messages("record"))
    except Exception as exc:
        raise TrackParseError(f"Invalid FIT file: {exc}") from exc

    points: list[dict[str, Any]] = []
    elevation_profile: list[dict[str, Any]] = []
    hr: list[int] = []
    cadence: list[int] = []
    power: list[int] = []

    start_time = None
    end_time = None
    last_distance_m = 0.0

    for rec in records:
        values = {d.name: d.value for d in rec}

        ts = values.get("timestamp")
        if ts is not None:
            if start_time is None:
                start_time = ts
            end_time = ts

        lat_raw = values.get("position_lat")
        lon_raw = values.get("position_long")
        lat = lat_raw * _SEMICIRCLE_TO_DEG if lat_raw is not None else None
        lon = lon_raw * _SEMICIRCLE_TO_DEG if lon_raw is not None else None
        ele = values.get("enhanced_altitude", values.get("altitude"))

        dist_m = values.get("distance")
        if dist_m is not None:
            last_distance_m = float(dist_m)

        if lat is not None and lon is not None:
            points.append(
                {"lat": lat, "lon": lon, "ele": ele, "time": ts.isoformat() if ts else None}
            )
            if dist_m is not None:
                elevation_profile.append(
                    {"distance_km": round(float(dist_m) / 1000.0, 4), "ele": ele}
                )

        if values.get("heart_rate") is not None:
            hr.append(int(values["heart_rate"]))
        if values.get("cadence") is not None:
            cadence.append(int(values["cadence"]))
        if values.get("power") is not None:
            power.append(int(values["power"]))

    if not records:
        raise TrackParseError("FIT file contains no record messages")

    # Prefer the session total_distance if available (more accurate than last record).
    distance_km = last_distance_m / 1000.0
    for session in fit.get_messages("session"):
        svals = {d.name: d.value for d in session}
        if svals.get("total_distance"):
            distance_km = float(svals["total_distance"]) / 1000.0
        break

    duration_seconds = 0
    if start_time and end_time:
        duration_seconds = int((end_time - start_time).total_seconds())

    telemetry = _summarize_telemetry(hr, cadence, power)

    return ParsedTrack(
        distance_km=round(distance_km, 4),
        duration_seconds=duration_seconds,
        start_time=start_time,
        track_points=points,
        elevation_profile=elevation_profile,
        telemetry=telemetry,
    )


def _summarize_telemetry(
    hr: list[int], cadence: list[int], power: list[int]
) -> dict[str, Any] | None:
    telemetry: dict[str, Any] = {}
    if hr:
        telemetry["heart_rate"] = {"avg": round(sum(hr) / len(hr), 1), "max": max(hr)}
    if cadence:
        telemetry["cadence"] = {"avg": round(sum(cadence) / len(cadence), 1), "max": max(cadence)}
    if power:
        telemetry["power"] = {"avg": round(sum(power) / len(power), 1), "max": max(power)}
    return telemetry or None
