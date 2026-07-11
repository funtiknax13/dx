from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import ClaimStatus


class GuestClaim(Base, TimestampMixin):
    """A registered runner claiming "this guest profile is me" — reviewed by an
    Admin, who on approval merges the guest's AttendanceRecords onto the claimant's
    account (see app.services.guest_service.merge_guest_into)."""

    __tablename__ = "guest_claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claimant_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[ClaimStatus] = mapped_column(
        Enum(ClaimStatus, native_enum=False, length=20),
        default=ClaimStatus.pending,
        nullable=False,
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    guest = relationship("User", foreign_keys=[guest_user_id])
    claimant = relationship("User", foreign_keys=[claimant_user_id])

    def __str__(self) -> str:
        return f"claim #{self.id}: {self.claimant} claims {self.guest}"
