from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, utcnow
from app.models.enums import FinishStatus, ModerationStatus, ResultSource


class Result(Base, TimestampMixin):
    """One result per AttendanceRecord (1:1). Re-upload overwrites in place."""

    __tablename__ = "results"

    id: Mapped[int] = mapped_column(primary_key=True)
    attendance_record_id: Mapped[int] = mapped_column(
        ForeignKey("attendance_records.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    pace_seconds_per_km: Mapped[float] = mapped_column(Float, nullable=False)

    # Recorded start time (from file when available) used for start-time auto-validation.
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source: Mapped[ResultSource] = mapped_column(
        Enum(ResultSource, native_enum=False, length=20), nullable=False
    )
    source_file: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Extracted from file when possible (JSON): track points, elevation profile, FIT telemetry.
    track_points: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    elevation_profile: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    telemetry: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    finish_status: Mapped[FinishStatus] = mapped_column(
        Enum(FinishStatus, native_enum=False, length=20), nullable=False
    )
    status: Mapped[ModerationStatus] = mapped_column(
        Enum(ModerationStatus, native_enum=False, length=20),
        default=ModerationStatus.pending,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    attendance_record = relationship("AttendanceRecord", back_populates="result")
