from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import Gender, PriorExperience, UserRole


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

    # Nullable = never answered. Empty string ("") is a distinct, deliberate
    # answer — "I checked the 'not in a club' box" — vs None ("never touched
    # this field") — both are needed to tell "answered" apart from "skipped"
    # for the profile-completeness gate (see profile_completeness_service).
    running_club: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # Self-reported at profile completion — see PriorExperience. Only shown
    # to accounts registered after this feature shipped; every pre-existing
    # account was backfilled to `multiple` in the introducing migration, so
    # this column reads as "unanswered" (None) only for a brand new
    # registration that hasn't finished their profile yet.
    prior_experience: Mapped[PriorExperience | None] = mapped_column(
        Enum(PriorExperience, native_enum=False, length=20), nullable=True
    )

    # When the user accepted the privacy policy (checkbox at registration).
    # Null for accounts predating this field and for guests (never registered
    # themselves, so never consented to anything).
    privacy_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

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
    # The real account a guest was merged into, if any — lets SQLAdmin show a
    # name instead of the bare merged_into_id.
    merged_into = relationship("User", remote_side=[id], foreign_keys=[merged_into_id])
    baseline = relationship(
        "RunnerBaseline", back_populates="runner", uselist=False, cascade="all, delete-orphan"
    )

    def __str__(self) -> str:  # nice label in SQLAdmin dropdowns
        suffix = " [guest]" if self.is_guest else ""
        return f"{self.first_name} {self.last_name} <{self.email}>{suffix}"
