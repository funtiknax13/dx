from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import case, or_, select

from app.api.deps import SessionDep
from app.models.city import City
from app.schemas.city import CityOut

router = APIRouter(prefix="/cities", tags=["cities"])


@router.get("/search", response_model=list[CityOut])
async def search_cities(
    session: SessionDep,
    q: Annotated[str, Query(min_length=2, max_length=80)],
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> list[City]:
    """Prefix search over the canonical city list (Russian and Latin names),
    biggest cities first — powers the profile's city picker. Public: city names
    aren't sensitive."""
    term = q.strip().lower()
    if len(term) < 2:
        return []
    # Substring match (so "челны" finds "Набережные Челны"), ranked by population
    # with a Russia boost — this is a Russian community, so a big RU city beats a
    # comparable foreign one (Саратов > Саргодха for "сар"), while a tiny RU
    # namesake still can't outrank a world capital (Paris stays top for "париж").
    # search_name/search_ascii are pre-lowercased (Unicode-correct) so plain LIKE
    # is locale-independent; the trgm GIN index accelerates the %contains% scan.
    contains = f"%{term}%"
    rank = City.population * case((City.country_code == "RU", 4), else_=1)
    stmt = (
        select(City)
        .where(or_(City.search_name.like(contains), City.search_ascii.like(contains)))
        .order_by(rank.desc())
        .limit(limit)
    )
    return list(await session.scalars(stmt))
