from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RunningClub(Base):
    """A running club, so the profile's "беговой клуб" field becomes a picker.
    Unlike the cities dictionary it's open: a runner may type a club that isn't
    listed yet and it's added here on save (with an empty city). `search_title`
    is a Python-lowercased copy for locale-independent case-insensitive matching
    (same trick as City.search_name)."""

    __tablename__ = "running_clubs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    search_title: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)

    def __str__(self) -> str:
        return f"{self.title} ({self.city})" if self.city else self.title
