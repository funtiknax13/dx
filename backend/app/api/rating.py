from typing import Literal

from fastapi import APIRouter

from app.api.deps import OptionalUser, SessionDep
from app.schemas.rating import RatingItem, RatingResponse
from app.services.profile_completeness_service import stats_access_lock
from app.services.rating_service import compute_rating

router = APIRouter(tags=["rating"])

TOP_N = 20


@router.get("/rating", response_model=RatingResponse)
async def rating(
    session: SessionDep, user: OptionalUser, period: Literal["all", "year", "month"] = "all"
) -> RatingResponse:
    lock_reason, missing_fields = stats_access_lock(user)
    if lock_reason is not None:
        return RatingResponse(
            period=period, entries=[], lock_reason=lock_reason, missing_fields=missing_fields
        )

    entries = await compute_rating(session, period)
    items = [
        RatingItem(
            rank=i,
            runner_id=e.runner_id,
            first_name=e.first_name,
            last_name=e.last_name,
            avatar=e.avatar,
            finished_count=e.finished_count,
        )
        for i, e in enumerate(entries, start=1)
    ]

    me = None
    if user is not None:
        mine = next((it for it in items if it.runner_id == user.id), None)
        if mine is not None and mine.rank > TOP_N:
            me = mine

    return RatingResponse(period=period, entries=items[:TOP_N], me=me)
