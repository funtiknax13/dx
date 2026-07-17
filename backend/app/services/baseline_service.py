from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.runner_baseline import RunnerBaseline


async def get_baseline(session: AsyncSession, runner_id: int) -> RunnerBaseline | None:
    result = await session.scalar(
        select(RunnerBaseline).where(RunnerBaseline.runner_id == runner_id)
    )
    return result


async def get_baselines(session: AsyncSession, runner_ids: list[int]) -> dict[int, RunnerBaseline]:
    """Bulk lookup for leaderboard/rating aggregation — one query instead of N."""
    if not runner_ids:
        return {}
    rows = await session.scalars(
        select(RunnerBaseline).where(RunnerBaseline.runner_id.in_(runner_ids))
    )
    return {b.runner_id: b for b in rows}


async def get_all_baselines(session: AsyncSession) -> dict[int, RunnerBaseline]:
    """All baselines, keyed by runner_id — used by all-time rating/leaderboard
    aggregation so a runner with a carry-over count but no *tracked*
    attendance yet still shows up, not just runners already in this app's
    AttendanceRecord data."""
    rows = await session.scalars(select(RunnerBaseline))
    return {b.runner_id: b for b in rows}
