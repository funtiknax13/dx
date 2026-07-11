from typing import Literal

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.schemas.rating import RatingItem, RatingResponse
from app.services.rating_service import compute_rating

router = APIRouter(tags=["rating"])


@router.get("/rating", response_model=RatingResponse)
async def rating(
    session: SessionDep, period: Literal["all", "year", "month"] = "all"
) -> RatingResponse:
    entries = await compute_rating(session, period)
    return RatingResponse(
        period=period,
        entries=[
            RatingItem(
                runner_id=e.runner_id,
                first_name=e.first_name,
                last_name=e.last_name,
                avatar=e.avatar,
                finished_count=e.finished_count,
            )
            for e in entries
        ],
    )
