"""The one definition of "has this group started / is this event over".

Signup, result entry, the upcoming/past tabs and the frontend's badges all
hang off the same moment, so it lives here rather than being re-derived per
endpoint (it used to be — two copies plus a third in list_events' SQL — and
they disagreed for groups without a start time). All comparisons are in
Cheboksary time (see app.core.timezone.EVENT_TZ)."""

from collections.abc import Iterable
from datetime import UTC, date, datetime

from app.core.timezone import EVENT_TZ, now_msk


def _aware(dt: datetime) -> datetime:
    # SQLite (tests) drops tzinfo — stored as UTC.
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def group_has_started(
    start_time: datetime | None, event_date: date, now: datetime | None = None
) -> bool:
    """A group with a start time has started the moment that instant passes.
    One without any can't be judged that way, so it counts as started only
    once its event's day is over — matching how list_events keeps such an
    event "upcoming" until midnight (see event_is_past)."""
    now = now or now_msk()
    if start_time is not None:
        return _aware(start_time) <= now
    return event_date < now.astimezone(EVENT_TZ).date()


def event_is_past(
    event_date: date, group_start_times: Iterable[datetime | None], now: datetime | None = None
) -> bool:
    """Past once its date is behind us, or — for an event dated today — once
    every one of its groups has a start time and the latest has passed. An
    event with no groups, or any group missing a start time, can't be judged
    that way and stays upcoming until midnight."""
    now = now or now_msk()
    today = now.astimezone(EVENT_TZ).date()
    if event_date < today:
        return True
    if event_date > today:
        return False
    starts = list(group_start_times)
    if not starts or any(s is None for s in starts):
        return False
    return max(_aware(s) for s in starts if s is not None) <= now
