from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import StaffPermission


class OrganizerPermission(Base, TimestampMixin):
    """One admin-tools moderation capability explicitly granted to an
    organizer — see StaffPermission for the catalog and permissions_service
    for how it's checked. Admin never needs a row here (permissions_for
    grants every value to admin implicitly). Granting/revoking is itself
    admin-only and not delegable (see admin.tools_permissions) — an
    organizer can never change their own or another organizer's access."""

    __tablename__ = "organizer_permissions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "permission", name="uq_organizer_permissions_user_id_permission"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission: Mapped[StaffPermission] = mapped_column(
        Enum(StaffPermission, native_enum=False, length=30), nullable=False
    )
    # Who granted it — kept for accountability; SET NULL (not CASCADE) so the
    # grant itself survives the granting admin's account being deleted later.
    granted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    user = relationship("User", foreign_keys=[user_id])
    granted_by = relationship("User", foreign_keys=[granted_by_id])

    def __str__(self) -> str:
        return f"{self.permission.value} → {self.user}"
