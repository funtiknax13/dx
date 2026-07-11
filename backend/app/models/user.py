from datetime import date

from sqlalchemy import Boolean, Date, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import Gender, UserRole


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Required profile fields
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=20), default=UserRole.runner, nullable=False
    )
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Optional profile fields
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    gender: Mapped[Gender | None] = mapped_column(
        Enum(Gender, native_enum=False, length=20), nullable=True
    )
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Guest accounts: auto-created from a CSV row that has no matching registered
    # email, so the run still shows up in the protocol/rating right away instead of
    # sitting invisible in a moderation queue. Not logins — synthetic email/password.
    # A real user can later claim one ("this is me"); once an admin approves the
    # claim, the guest's AttendanceRecords are reassigned to the real account and
    # `merged_into_id` is set (the guest row itself is kept for audit, not deleted).
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    merged_into_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    signups = relationship("Signup", back_populates="runner", cascade="all, delete-orphan")
    attendance_records = relationship("AttendanceRecord", back_populates="runner")

    def __str__(self) -> str:  # nice label in SQLAdmin dropdowns
        suffix = " [guest]" if self.is_guest else ""
        return f"{self.first_name} {self.last_name} <{self.email}>{suffix}"
