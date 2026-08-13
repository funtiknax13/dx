from pydantic import BaseModel, ConfigDict


class RunningClubOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    city: str | None
