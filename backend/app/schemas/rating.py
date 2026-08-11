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
    # Full ranking size (all pages) and the current page, so the frontend can
    # build a pager. 0-activity runners are already excluded (see compute_rating).
    total: int = 0
    page: int = 1
    page_size: int = 20
    # The requesting user's own entry, only when they're authenticated and NOT
    # on the current page — already visible in `entries` otherwise. Its `rank`
    # lets the frontend point at the page the user is on.
    me: RatingItem | None = None
    # None = unlocked. "anonymous" or "profile_incomplete" — see
    # profile_completeness_service.stats_access_lock. When locked, entries/me
    # are always empty; the frontend renders the locked state instead.
    lock_reason: str | None = None
    missing_fields: list[str] = []
