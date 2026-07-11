from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Group(Base, TimestampMixin):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )

    location: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # distance code / group name

    # Pace range stored as human "mm:ss" strings (e.g. 5:40 .. 5:30).
    pace_min: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pace_max: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Reference values used to auto-validate uploaded results.
    target_distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    route_gpx: Mapped[str | None] = mapped_column(String(500), nullable=True)

    event = relationship("Event", back_populates="groups")
    signups = relationship("Signup", back_populates="group", cascade="all, delete-orphan")
    attendance_records = relationship(
        "AttendanceRecord", back_populates="group", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return f"{self.name} @ {self.location}"
