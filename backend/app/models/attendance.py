from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import FinishStatus


class AttendanceRecord(Base, TimestampMixin):
    """Source of truth that someone actually ran. Created from CSV import, initially
    without an account link (runner_id null) until an admin matches it."""

    __tablename__ = "attendance_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )

    raw_name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)

    runner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    finish_status: Mapped[FinishStatus] = mapped_column(
        Enum(FinishStatus, native_enum=False, length=20),
        default=FinishStatus.finished,
        nullable=False,
    )

    group = relationship("Group", back_populates="attendance_records")
    runner = relationship("User", back_populates="attendance_records")
    result = relationship(
        "Result",
        back_populates="attendance_record",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __str__(self) -> str:
        return f"{self.raw_name} (group {self.group_id})"
