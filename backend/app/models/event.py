from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_image: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    creator = relationship("User")
    groups = relationship("Group", back_populates="event", cascade="all, delete-orphan")
    photos = relationship("EventPhoto", back_populates="event", cascade="all, delete-orphan")

    def __str__(self) -> str:
        return self.title


class EventPhoto(Base, TimestampMixin):
    __tablename__ = "event_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    image: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uploaded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    event = relationship("Event", back_populates="photos")
