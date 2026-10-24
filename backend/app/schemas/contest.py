from datetime import datetime

from pydantic import BaseModel


class ContestFieldOut(BaseModel):
    id: int
    position: int
    label: str
    description: str | None
    field_type: str
    required: bool
    visible_to_voters: bool
    # Only meaningful for field_type == "multi_select".
    options: list[str] | None


class ContestSummary(BaseModel):
    id: int
    title: str
    cover_image: str | None
    phase: str
    submissions_open_at: datetime | None
    submissions_close_at: datetime | None
    voting_open_at: datetime | None
    voting_close_at: datetime | None


class ContestDetail(BaseModel):
    id: int
    title: str
    description: str | None
    cover_image: str | None
    phase: str
    submissions_open_at: datetime | None
    submissions_close_at: datetime | None
    voting_open_at: datetime | None
    voting_close_at: datetime | None
    votes_visible_live: bool
    results_published: bool
    # Null = unlimited — lets the frontend show/hide "add another entry"
    # without a separate request.
    max_entries_per_runner: int | None
    # Only populated once the phase has moved past "upcoming" — before that
    # a contest is a pure teaser, no conditions shown (see contest_service).
    fields: list[ContestFieldOut] | None


class ContestEntryValueOut(BaseModel):
    field_id: int
    value: str | None


class MyEntryOut(BaseModel):
    id: int
    status: str
    rejection_reason: str | None
    submitted_at: datetime
    placement: int | None
    values: list[ContestEntryValueOut]


class PublicEntryOut(BaseModel):
    id: int
    runner_id: int
    runner_name: str
    avatar: str | None
    placement: int | None
    vote_count: int | None
    # Only the fields marked visible_to_voters — see ContestField.
    values: list[ContestEntryValueOut]


class ContestEntriesOut(BaseModel):
    entries: list[PublicEntryOut]
    votes_visible: bool
    my_vote_entry_id: int | None
