from pydantic import BaseModel


class LeaderboardItem(BaseModel):
    rank: int
    runner_id: int
    first_name: str
    last_name: str
    avatar: str | None
    value: float


class LeaderboardResponse(BaseModel):
    metric: str
    period: str
    entries: list[LeaderboardItem]
    # The requesting user's own entry, only when authenticated and outside
    # `entries` (past the top-N cutoff) — already visible there otherwise.
    me: LeaderboardItem | None = None
    # None = unlocked. "anonymous" or "profile_incomplete" — see
    # profile_completeness_service.stats_access_lock. When locked, entries/me
    # are always empty; the frontend renders the locked state instead.
    lock_reason: str | None = None
    missing_fields: list[str] = []
