from typing import Any

import gpxpy

from app.services.track_types import ParsedTrack


class TrackParseError(ValueError):
    """Raised when an uploaded track file cannot be parsed."""


def parse_gpx(content: str | bytes) -> ParsedTrack:
    """Parse a GPX document into a normalized ParsedTrack.

    Used both for runner results and for a group's planned route (Group.route_gpx),
    per CLAUDE.md — the same parser feeds the map/elevation JSON for the frontend.
    """
    text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
    try:
        gpx = gpxpy.parse(text)
    except Exception as exc:  # gpxpy raises a variety of parse errors
        raise TrackParseError(f"Invalid GPX file: {exc}") from exc

    points: list[dict[str, Any]] = []
    for track in gpx.tracks:
        for segment in track.segments:
            for p in segment.points:
                points.append(
                    {
                        "lat": p.latitude,
                        "lon": p.longitude,
                        "ele": p.elevation,
                        "time": p.time.isoformat() if p.time else None,
                    }
                )
    # Fall back to routes / waypoints if there are no track segments.
    if not points:
        for route in gpx.routes:
            for rp in route.points:
                points.append(
                    {"lat": rp.latitude, "lon": rp.longitude, "ele": rp.elevation, "time": None}
                )

    if not points:
        raise TrackParseError("GPX file contains no track points")

    distance_km = gpx.length_3d() / 1000.0 if gpx.length_3d() else gpx.length_2d() / 1000.0

    # Duration from moving/elapsed time bounds.
    duration_seconds = 0
    start_time = None
    time_bounds = gpx.get_time_bounds()
    if time_bounds.start_time and time_bounds.end_time:
        start_time = time_bounds.start_time
        duration_seconds = int((time_bounds.end_time - time_bounds.start_time).total_seconds())

    elevation_profile = _build_elevation_profile(gpx)

    return ParsedTrack(
        distance_km=round(distance_km, 4),
        duration_seconds=duration_seconds,
        start_time=start_time,
        track_points=points,
        elevation_profile=elevation_profile,
        telemetry=None,
    )


def _build_elevation_profile(gpx: Any) -> list[dict[str, Any]]:
    profile: list[dict[str, Any]] = []
    cumulative_m = 0.0
    prev = None
    for track in gpx.tracks:
        for segment in track.segments:
            for p in segment.points:
                if prev is not None:
                    cumulative_m += p.distance_2d(prev) or 0.0
                profile.append(
                    {"distance_km": round(cumulative_m / 1000.0, 4), "ele": p.elevation}
                )
                prev = p
    return profile
