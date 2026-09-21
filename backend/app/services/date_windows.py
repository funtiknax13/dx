from datetime import date

from app.core.timezone import today_msk


def current_year() -> int:
    return today_msk().year


def calendar_window(period: str) -> tuple[date, date] | None:
    """(start, today) for "year"/"month" — a *calendar* window (Jan 1 / the
    1st of this month, through today), shared by rating_service and
    leaderboard_service so "this year"/"this month" mean the same thing
    everywhere in the app. None for "all" (unwindowed)."""
    today = today_msk()
    if period == "year":
        return date(today.year, 1, 1), today
    if period == "month":
        return date(today.year, today.month, 1), today
    return None
