"""In-memory adaptive attempt tracker for the captcha gate.

Records timestamped events (failed logins, registration attempts) per
`scope:ip` in a sliding window, so a captcha can be required only once an IP
looks abusive. Prod runs a single uvicorn worker with no Redis, so a plain
module-level dict is enough — it resets on restart, which is fine for abuse
throttling. All access is from the async event loop with no awaits between
read and write, so no locking is needed. Old entries are pruned lazily on
each touch, bounding memory to "IPs active within the window".
"""

import time

from app.core.config import settings

_events: dict[str, list[float]] = {}


def _window_seconds() -> float:
    return settings.captcha_attempt_window_minutes * 60


def _prune(key: str, now: float) -> list[float]:
    cutoff = now - _window_seconds()
    times = [t for t in _events.get(key, []) if t >= cutoff]
    if times:
        _events[key] = times
    else:
        _events.pop(key, None)
    return times


def record(scope: str, ip: str | None) -> None:
    if not ip:
        return
    key = f"{scope}:{ip}"
    now = time.monotonic()
    times = _prune(key, now)
    times.append(now)
    _events[key] = times


def count(scope: str, ip: str | None) -> int:
    if not ip:
        return 0
    return len(_prune(f"{scope}:{ip}", time.monotonic()))


def reset(scope: str, ip: str | None) -> None:
    if ip:
        _events.pop(f"{scope}:{ip}", None)


def should_challenge(scope: str, ip: str | None, threshold: int) -> bool:
    """True once an IP has reached the failure/attempt threshold for a scope."""
    return count(scope, ip) >= threshold


def clear_all() -> None:
    """Test helper — wipe all tracked state between cases."""
    _events.clear()
