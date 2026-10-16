from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import ContestFieldType, ModerationStatus


class Contest(Base, TimestampMixin):
    """A timed, voted community contest (route design, photo, etc.) run as
    its own event type — not a running Event/Group, so it stays a separate
    entity rather than overloading one that's all about pace groups and
    protocols. Its visible phase (upcoming/open/closed/voting/results) is a
    pure function of `is_published` + the four window timestamps below,
    computed in contest_service — never stored, so it can't drift out of
    sync with "what time is it now" the way a hand-set status could."""

    __tablename__ = "contests"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # Off (the default) while the constructor is still being assembled: the
    # contest doesn't exist publicly at all, not even as a teaser — "запустить
    # конкурс" flips this on. Once on, the window timestamps below decide
    # whether what's shown is a teaser, the submission form, "submissions
    # closed", voting, or results — see contest_service.contest_phase.
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    submissions_open_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    submissions_close_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    voting_open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voting_close_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Whether vote tallies are visible *while voting is still open* — off by
    # default (the common case: reveal only once voting closes, so an early
    # leader doesn't snowball votes). Approved entries themselves are always
    # visible once voting opens regardless of this flag; this only gates the
    # numbers.
    votes_visible_live: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Set by an admin action (not derived from voting_close_at) — ranking by
    # raw vote count is only ever a suggestion the admin confirms, so a
    # contest can sit in "подводим итоги" for a while after voting closes
    # without exposing anything, and ties/disqualifications get a human
    # decision rather than an automatic tie-break rule.
    results_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    creator = relationship("User")
    fields = relationship(
        "ContestField",
        back_populates="contest",
        cascade="all, delete-orphan",
        order_by="ContestField.position",
    )
    entries = relationship("ContestEntry", back_populates="contest", cascade="all, delete-orphan")
    votes = relationship("ContestVote", back_populates="contest", cascade="all, delete-orphan")

    def __str__(self) -> str:
        return self.title


class ContestField(Base, TimestampMixin):
    """One item of the contest "constructor" — what a participant must fill
    in/upload, and whether it's shown on the public voting page. See
    ContestFieldType for the fixed set of supported kinds."""

    __tablename__ = "contest_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    contest_id: Mapped[int] = mapped_column(
        ForeignKey("contests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_type: Mapped[ContestFieldType] = mapped_column(
        Enum(ContestFieldType, native_enum=False, length=20), nullable=False
    )
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # The "что публиковать на страничке голосования" checkbox — off hides
    # this field's value from voters/the public entry list while still
    # collecting and showing it to the admin during moderation.
    visible_to_voters: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    contest = relationship("Contest", back_populates="fields")

    def __str__(self) -> str:
        return f"#{self.position + 1}: {self.label}"


class ContestEntry(Base, TimestampMixin):
    """One participant's submission to one contest — at most one per runner
    per contest (uq below), re-submittable in place after a rejection rather
    than creating a second row."""

    __tablename__ = "contest_entries"
    __table_args__ = (
        UniqueConstraint("contest_id", "runner_id", name="uq_contest_entry_runner"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contest_id: Mapped[int] = mapped_column(
        ForeignKey("contests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    runner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[ModerationStatus] = mapped_column(
        Enum(ModerationStatus, native_enum=False, length=20),
        default=ModerationStatus.pending,
        nullable=False,
    )
    # Kept on the row (not just sent as a ticket, unlike Result's rejection
    # message) so the runner sees exactly what to fix right on their own
    # resubmit form, not only in a support ticket they might have missed.
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When this entry was last (re)submitted — distinct from created_at
    # (first creation) and updated_at (bumped by admin actions too).
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Final ranking, set by an admin confirming results (see Contest.
    # results_published_at) — not auto-derived from vote counts, so a tie or
    # a late disqualification is a human call. Null until decided.
    placement: Mapped[int | None] = mapped_column(Integer, nullable=True)

    contest = relationship("Contest", back_populates="entries")
    runner = relationship("User")
    values = relationship(
        "ContestEntryValue", back_populates="entry", cascade="all, delete-orphan"
    )
    votes = relationship("ContestVote", back_populates="entry", cascade="all, delete-orphan")

    def __str__(self) -> str:
        return f"entry #{self.id} ({self.runner})"


class ContestEntryValue(Base, TimestampMixin):
    """One field's worth of data on one entry — text/number/url as the raw
    string, image/gpx as the saved media path (see media_service)."""

    __tablename__ = "contest_entry_values"
    __table_args__ = (
        UniqueConstraint("entry_id", "field_id", name="uq_contest_entry_value_field"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("contest_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_id: Mapped[int] = mapped_column(
        ForeignKey("contest_fields.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[str | None] = mapped_column(Text, nullable=True)

    entry = relationship("ContestEntry", back_populates="values")
    field = relationship("ContestField")


class ContestVote(Base, TimestampMixin):
    """One runner's vote for one entry — at most one vote per runner per
    contest (uq below), not per entry, so switching your pick before voting
    closes just moves the same row rather than adding a second vote."""

    __tablename__ = "contest_votes"
    __table_args__ = (UniqueConstraint("contest_id", "voter_id", name="uq_contest_vote_voter"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    contest_id: Mapped[int] = mapped_column(
        ForeignKey("contests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    voter_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("contest_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )

    contest = relationship("Contest", back_populates="votes")
    entry = relationship("ContestEntry", back_populates="votes")
    voter = relationship("User")
