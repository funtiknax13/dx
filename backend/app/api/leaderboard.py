from typing import Literal

from fastapi import APIRouter

from app.api.deps import OptionalUser, SessionDep
from app.schemas.leaderboard import LeaderboardItem, LeaderboardResponse
from app.services.leaderboard_service import compute_leaderboard, compute_streak_leaderboard

router = APIRouter(tags=["leaderboard"])

TOP_N = 20


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def leaderboard(
    session: SessionDep,
    user: OptionalUser,
    metric: Literal["dx", "km", "streak"] = "dx",
    period: Literal["all", "year", "month"] = "all",
) -> LeaderboardResponse:
    if metric == "streak":
        entries = await compute_streak_leaderboard(session)
        period = "all"  # streak is inherently period-agnostic
    else:
        entries = await compute_leaderboard(session, metric, period)

    items = [
        LeaderboardItem(
            rank=i,
            runner_id=e.runner_id,
            first_name=e.first_name,
            last_name=e.last_name,
            avatar=e.avatar,
            value=e.value,
        )
        for i, e in enumerate(entries, start=1)
    ]

    me = None
    if user is not None:
        mine = next((it for it in items if it.runner_id == user.id), None)
        if mine is not None and mine.rank > TOP_N:
            me = mine

    return LeaderboardResponse(metric=metric, period=period, entries=items[:TOP_N], me=me)
