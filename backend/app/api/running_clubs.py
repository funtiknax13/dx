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
    q: Annotated[str, Query(min_length=1, max_length=150)],
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> list[RunningClub]:
    """Substring search over known running clubs — powers the profile's club
    picker. Public: club names aren't sensitive. search_title is pre-lowercased
    so plain LIKE is locale-independent."""
    term = q.strip().lower()
    if not term:
        return []
    stmt = (
        select(RunningClub)
        .where(RunningClub.search_title.like(f"%{term}%"))
        .order_by(RunningClub.title)
        .limit(limit)
    )
    return list(await session.scalars(stmt))
