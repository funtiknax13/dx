from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttendanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    raw_name: str
    raw_email: str | None
    raw_phone: str | None
    runner_id: int | None
    finish_status: str


class CsvImportResponse(BaseModel):
    created: int
    skipped_duplicates: int
    skipped_empty: int


class MatchRequest(BaseModel):
    runner_id: int


class UnmatchedRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    raw_name: str
    raw_email: str | None
    raw_phone: str | None
    created_at: datetime
