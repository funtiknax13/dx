from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import ModerationStatus


class ProfileEditRequest(Base, TimestampMixin):
    """Post-moderation for the whole profile form (name, birthday, city, gender,
    phone, running club, guardian contacts) — see CLAUDE.md/session discussion:
    in a community where runners train together and recognize each other, none
    of this should be silently self-editable.

    `User`'s own columns always hold the last *approved* values — nothing here
    ever changes them directly except `profile_review_service.approve`. A brand
    new registration writes a placeholder name onto `User` (see
    profile_review_service.PLACEHOLDER_FIRST_NAME) and puts the real submitted
    name here instead; every later `PATCH /users/me` diffs against the current
    approved values and stages only what actually changed. Only one row per
    user is ever `pending` at a time — a new submission while one is still
    pending replaces it (see submit_for_review).
    """

    __tablename__ = "profile_edit_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # {field_name: new_value}, JSON-safe (dates as ISO strings) — only the
    # fields actually being proposed, never a full profile snapshot.
    changes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[ModerationStatus] = mapped_column(
        Enum(ModerationStatus, native_enum=False, length=20),
        default=ModerationStatus.pending,
        nullable=False,
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", foreign_keys=[user_id])

    def __str__(self) -> str:
        return f"profile edit #{self.id} for {self.user} ({self.status})"
