from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class City(Base):
    """A canonical populated place (from GeoNames) with coordinates, so the
    free-text city field can become a structured selection — and later drive a
    participants map. `id` is the GeoNames geonameid (stable, so re-imports
    upsert cleanly). `name` is the Russian-preferred display name, `name_ascii`
    the Latin form so search matches both "Москва" and "Moscow"."""

    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ascii: Mapped[str] = mapped_column(String(200), nullable=False)
    # Python-lowercased copies for locale-independent case-insensitive search
    # (Postgres lower()/ILIKE doesn't fold Cyrillic under every DB locale).
    search_name: Mapped[str] = mapped_column(String(200), nullable=False)
    search_ascii: Mapped[str] = mapped_column(String(200), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    region: Mapped[str | None] = mapped_column(String(160), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    population: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __str__(self) -> str:
        parts = [self.name]
        if self.region:
            parts.append(self.region)
        if self.country:
            parts.append(self.country)
        return ", ".join(parts)
