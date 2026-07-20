from pydantic import BaseModel


class RatingItem(BaseModel):
    rank: int
    runner_id: int
    first_name: str
    last_name: str
    avatar: str | None
    finished_count: int


class RatingResponse(BaseModel):
    period: str
    entries: list[RatingItem]
    # The requesting user's own entry, only when they're authenticated and
    # outside `entries` (i.e. past the top-N cutoff) — already visible in
    # `entries` otherwise, no need to repeat it.
    me: RatingItem | None = None
    # None = unlocked. "anonymous" or "profile_incomplete" — see
    # profile_completeness_service.stats_access_lock. When locked, entries/me
    # are always empty; the frontend renders the locked state instead.
    lock_reason: str | None = None
    missing_fields: list[str] = []
