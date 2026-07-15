from typing import Literal

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.schemas.leaderboard import LeaderboardItem, LeaderboardResponse
from app.services.leaderboard_service import compute_leaderboard, compute_streak_leaderboard

router = APIRouter(tags=["leaderboard"])


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def leaderboard(
    session: SessionDep,
    metric: Literal["dx", "km", "streak"] = "dx",
    period: Literal["all", "year", "month"] = "all",
) -> LeaderboardResponse:
    if metric == "streak":
        entries = await compute_streak_leaderboard(session)
        period = "all"  # streak is inherently period-agnostic
    else:
        entries = await compute_leaderboard(session, metric, period)
    return LeaderboardResponse(
        metric=metric,
        period=period,
        entries=[
            LeaderboardItem(
                rank=i,
                runner_id=e.runner_id,
                first_name=e.first_name,
                last_name=e.last_name,
                avatar=e.avatar,
                value=e.value,
            )
            for i, e in enumerate(entries, start=1)
        ],
    )
