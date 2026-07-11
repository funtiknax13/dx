from pydantic import BaseModel


class RatingItem(BaseModel):
    runner_id: int
    first_name: str
    last_name: str
    avatar: str | None
    finished_count: int


class RatingResponse(BaseModel):
    period: str
    entries: list[RatingItem]
