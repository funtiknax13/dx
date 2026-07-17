from pydantic import BaseModel


class BaselineCsvImportResponse(BaseModel):
    created: int
    updated: int
    skipped_empty: int
    skipped_invalid_number: int
    auto_matched: int
    guests_created: int
    guests_reused: int
    merged_redirects: int
