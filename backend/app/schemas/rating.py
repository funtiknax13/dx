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
