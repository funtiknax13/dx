from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.running_club import RunningClub


async def ensure_running_club(
    session: AsyncSession, title: str | None, city: str | None = None
) -> RunningClub | None:
    """Return the club row for `title`, creating it (with an optional city) if it
    isn't listed yet — this is what lets a runner type a club that doesn't exist.
    Matching is case-insensitive on the pre-lowered search_title. An empty title
    (the "not in a club" answer) creates nothing. The row is flushed so its
    canonical `title` is available to the caller."""
    if title is None:
        return None
    clean = title.strip()
    if not clean:
        return None
    key = clean.lower()
    club = await session.scalar(
        select(RunningClub).where(RunningClub.search_title == key)
    )
    if club is not None:
        # Fill in a city if we learn one and the row didn't have it yet.
        if city and not club.city:
            club.city = city.strip() or None
        return club
    club = RunningClub(title=clean, search_title=key, city=(city or "").strip() or None)
    session.add(club)
    await session.flush()
    return club
