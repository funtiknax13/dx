from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.services.event_time import event_is_past, group_has_started

MSK = ZoneInfo("Europe/Moscow")


def msk(day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=MSK)


EVENT_DAY = date(2026, 9, 21)
START = msk(21, 9, 30)  # a 09:30 Moscow start = 06:30 UTC


def test_group_not_started_in_the_small_hours_of_event_day() -> None:
    """The frontend used to flip the event to "past" at 03:00 Moscow time on
    the day (midnight UTC) — six hours before a 09:30 start."""
    assert group_has_started(START, EVENT_DAY, now=msk(21, 3, 30)) is False


def test_group_started_once_its_start_time_passes() -> None:
    assert group_has_started(START, EVENT_DAY, now=msk(21, 9, 29)) is False
    assert group_has_started(START, EVENT_DAY, now=msk(21, 9, 30)) is True
    assert group_has_started(START, EVENT_DAY, now=msk(21, 12)) is True


def test_group_start_time_from_a_tz_naive_db_is_read_as_utc() -> None:
    naive_utc = datetime(2026, 9, 21, 6, 30)  # SQLite drops tzinfo; stored as UTC
    assert group_has_started(naive_utc, EVENT_DAY, now=msk(21, 9, 29)) is False
    assert group_has_started(naive_utc, EVENT_DAY, now=msk(21, 9, 31)) is True


def test_group_now_in_utc_is_compared_in_moscow_time() -> None:
    utc_now = datetime(2026, 9, 21, 6, 45, tzinfo=UTC)  # 09:45 Moscow
    assert group_has_started(START, EVENT_DAY, now=utc_now) is True


def test_untimed_group_started_only_once_the_event_day_is_over() -> None:
    assert group_has_started(None, EVENT_DAY, now=msk(21, 0, 5)) is False
    assert group_has_started(None, EVENT_DAY, now=msk(21, 23, 59)) is False
    assert group_has_started(None, EVENT_DAY, now=msk(22, 0, 1)) is True


def test_untimed_group_day_over_is_judged_in_moscow_not_utc() -> None:
    # 21:30 UTC on the 21st is already 00:30 on the 22nd in Cheboksary.
    utc_now = datetime(2026, 9, 21, 21, 30, tzinfo=UTC)
    assert group_has_started(None, EVENT_DAY, now=utc_now) is True


def test_event_past_and_future_by_date() -> None:
    assert event_is_past(date(2026, 9, 20), [START], now=msk(21, 8)) is True
    assert event_is_past(date(2026, 9, 22), [START], now=msk(21, 23)) is False


def test_event_today_is_past_only_after_its_latest_group_starts() -> None:
    later = msk(21, 11, 0)
    assert event_is_past(EVENT_DAY, [START, later], now=msk(21, 3, 30)) is False
    assert event_is_past(EVENT_DAY, [START, later], now=msk(21, 10, 0)) is False
    assert event_is_past(EVENT_DAY, [START, later], now=msk(21, 11, 0)) is True


def test_event_today_with_an_untimed_group_or_no_groups_stays_upcoming() -> None:
    assert event_is_past(EVENT_DAY, [START, None], now=msk(21, 20)) is False
    assert event_is_past(EVENT_DAY, [], now=msk(21, 20)) is False
    assert event_is_past(EVENT_DAY, [START, None], now=msk(22, 0, 1)) is True
