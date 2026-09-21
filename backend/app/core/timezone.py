from datetime import date, datetime
from zoneinfo import ZoneInfo

# The community is Cheboksary-only — every event/group time is a Cheboksary
# wall-clock time, and every viewer must see that same number regardless of
# their own browser's timezone. Russia hasn't observed DST since 2014, so
# this is a fixed UTC+3, but ZoneInfo keeps it correct if that ever changes
# rather than hardcoding the offset.
EVENT_TZ = ZoneInfo("Europe/Moscow")


def now_msk() -> datetime:
    return datetime.now(EVENT_TZ)


def today_msk() -> date:
    """ "Today" for anything tied to an event date — an event dated the 21st
    is on the 21st in Cheboksary from 00:00 Moscow time, not from 03:00 (when
    UTC's calendar date catches up), so `date.today()` / `datetime.now(UTC)
    .date()` are wrong for the first three hours of every day."""
    return now_msk().date()
