from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import SessionDep
from app.models.running_club import RunningClub
from app.schemas.running_club import RunningClubOut

router = APIRouter(prefix="/running-clubs", tags=["running-clubs"])


@router.get("/search", response_model=list[RunningClubOut])
async def search_running_clubs(
    session: SessionDep,
    q: Annotated[str, Query(max_length=150)] = "",
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> list[RunningClub]:
    """Substring search over known running clubs — powers the profile's club
    picker. A blank `q` lists every club (alphabetically, capped at `limit`)
    rather than nothing, so the picker has something to show the moment the
    field gains focus, before the runner has typed anything — otherwise a
    runner who mistypes a club that's already listed never sees the existing
    options and just creates a near-duplicate entry. Public: club names
    aren't sensitive. search_title is pre-lowercased so plain LIKE is
    locale-independent."""
    term = q.strip().lower()
    stmt = select(RunningClub).order_by(RunningClub.title).limit(limit)
    if term:
        stmt = stmt.where(RunningClub.search_title.like(f"%{term}%"))
    return list(await session.scalars(stmt))
