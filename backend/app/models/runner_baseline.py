from sqlalchemy import Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class RunnerBaseline(Base, TimestampMixin):
    """Admin-entered carry-over stats from before this platform existed — the
    organizer doesn't want to backfill years of historical CSVs, but a
    long-time runner's totals should still reflect their real history.

    Folded in as a flat addition to lifetime totals only (profile stats and
    the all-time rating/leaderboard) — never into streaks or year/month
    windowed numbers, since those need real dated events, not just a count.

    Admin-only: never exposed through any self-service endpoint, editable
    only via SQLAdmin.
    """

    __tablename__ = "runner_baselines"

    id: Mapped[int] = mapped_column(primary_key=True)
    runner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    dx_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_km: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    runner = relationship("User", back_populates="baseline")

    def __str__(self) -> str:
        return f"{self.dx_count} DX / {self.total_runs} пробежек / {self.total_km:g} км"
