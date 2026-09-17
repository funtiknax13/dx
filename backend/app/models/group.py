from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.event import Event


class Group(Base, TimestampMixin):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )

    location: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # distance code / group name

    # Optional coordinates for the start location — the text `location` field
    # above stays the source of truth for display, these just add a map/link.
    # Nullable: an organizer can add a GPX route without ever setting these.
    start_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_lng: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Shared tag across pace-subgroups of the same real-world distance within
    # one event (e.g. "X-33" for both "Х-33 группа #1" and "#2") — lets the
    # protocol endpoint merge them into one leaderboard. Null means "no family",
    # i.e. this group's protocol stands alone.
    distance_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Legacy single pace range as human "mm:ss" strings (e.g. 5:40 .. 5:30).
    # Superseded by `pace_segments` (below): kept for groups created before the
    # structured plan existed and as a display fallback when no segments are set.
    pace_min: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pace_max: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Structured pace plan: an ordered list of segments so a group can describe a
    # workout whose pace changes across the run (warm-up / target / cool-down, a
    # progression, …) rather than a single flat range. Each item:
    #   {"label": str, "distance_km": float|None, "pace_from": str|None,
    #    "pace_to": str|None}
    # Display-only (never feeds result auto-validation, same as the old range).
    # Null / empty means "fall back to pace_min..pace_max".
    pace_segments: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)

    # Reference values used to auto-validate uploaded results.
    target_distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    route_gpx: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Off for e.g. a social/kids/non-competitive group whose finishers
    # shouldn't count toward community rating standings.
    counts_toward_rating: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    event = relationship("Event", back_populates="groups")
    signups = relationship("Signup", back_populates="group", cascade="all, delete-orphan")
    attendance_records = relationship(
        "AttendanceRecord", back_populates="group", cascade="all, delete-orphan"
    )

    # A correlated subquery, not the `event` relationship — rides along with
    # every plain `select(Group)` as an ordinary column (computed by the DB
    # in the same query), so it's safe to read in __str__ below whenever this
    # row actually came from a query. The `event` relationship itself is
    # never safe there: SQLAdmin populates this model's own FK dropdowns
    # (e.g. AttendanceRecord's "Group" field) via a bare, non-eager-loading
    # query, and calling __str__ on those rows while still inside that
    # query's async context would hit "MissingGreenlet" — same class of bug
    # the comment on AttendanceRecord.__str__ documents.
    event_date = column_property(
        select(Event.date).where(Event.id == event_id).correlate_except(Event).scalar_subquery()
    )

    def __str__(self) -> str:
        # A row just constructed and flushed in Python (not yet re-fetched by
        # a SELECT) has event_date unset — unlike a plain column, a
        # column_property doesn't get a value until the DB actually computes
        # it, so touching it here would itself trigger the same kind of
        # implicit-IO crash this whole approach exists to avoid. Checking
        # `unloaded` first means __str__ never queries anything on its own;
        # it just uses the date when a query already put it there.
        unloaded = sa_inspect(self).unloaded
        when = self.event_date.strftime("%d.%m.%Y") if "event_date" not in unloaded else None
        if when:
            return f"{self.name} @ {self.location} ({when})"
        return f"{self.name} @ {self.location}"
