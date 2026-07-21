from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import TicketStatus


class SupportTicket(Base, TimestampMixin):
    """A support thread — from a logged-in user, or anonymous ("guest" in
    the product sense, not User.is_guest — someone who can't log in, e.g.
    stuck registering, so has no account to attach the ticket to).

    created_by_user_id is nullable and ON DELETE SET NULL: if the reporter
    later deletes their account (see DELETE /users/me), the ticket survives
    as an anonymized record rather than vanishing, matching how
    AttendanceRecord is anonymized rather than deleted (see CLAUDE.md).
    Anonymous tickets never get a reply *in the app* — there's no account to
    deliver one to — so admin-tools simply doesn't offer a reply form for
    them; staff can still read the message and any guest_contact given and
    follow up outside the platform.
    """

    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, native_enum=False, length=20),
        default=TicketStatus.open,
        nullable=False,
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    guest_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    guest_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_by = relationship("User")
    messages = relationship(
        "SupportMessage",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="SupportMessage.id",
    )

    def __str__(self) -> str:
        who = self.created_by.email if self.created_by else (self.guest_name or "аноним")
        return f"тикет #{self.id} ({who})"


class SupportMessage(Base, TimestampMixin):
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Null for an anonymous reporter's own messages; always set for staff
    # replies and for a logged-in reporter's messages.
    sender_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # When the *other* side (staff message -> reporter, reporter message ->
    # staff) viewed it — drives both the reporter's "new reply" badge and
    # admin-tools' unread-tickets badge. Read state is shared across all
    # staff (a team inbox, not per-agent), same as the survey-responses badge.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ticket = relationship("SupportTicket", back_populates="messages")
    sender = relationship("User")
