from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Signup(Base, TimestampMixin):
    """Intent to participate in a group. Independent of actual attendance."""

    __tablename__ = "signups"
    # A runner may only be signed up for one group per event — event_id is
    # denormalized from group.event_id (kept in sync in app.api.signups) so
    # this can be a real DB constraint instead of an app-level race.
    __table_args__ = (UniqueConstraint("runner_id", "event_id", name="uq_signup_runner_event"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    runner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )

    runner = relationship("User", back_populates="signups")
    group = relationship("Group", back_populates="signups")
    event = relationship("Event")
