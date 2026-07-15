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
