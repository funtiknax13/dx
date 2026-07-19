from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class RunnerBaseline(Base, TimestampMixin):
    """Admin-entered carry-over stats from before this platform existed — the
    organizer doesn't want to backfill years of historical CSVs, but a
    long-time runner's totals should still reflect their real history.

    dx_count/total_runs/total_km are folded in as a flat addition to
    lifetime totals only (profile stats and the all-time rating/leaderboard)
    — never into streaks or year/month windowed numbers, since those need
    real dated events, not just a count.

    dx_count_this_year/km_this_year are a *subset* of dx_count/total_km, not
    an addition on top — e.g. dx_count=255 overall, of which
    dx_count_this_year=26 happened within `baseline_year`. They exist solely
    to feed the "this year" rating/leaderboard bucket (never "this month" —
    a once-entered number can't be attributed to a specific month), and only
    apply while the current calendar year equals `baseline_year`; once the
    year rolls over they're simply inert until an admin updates them (and
    baseline_year) for the new year.

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

    # When this runner's *actual* first run happened, pre-dating anything
    # tracked by this platform — lets the profile's "первая пробежка" stat
    # show the real date instead of the first tracked (CSV-imported) one.
    first_run_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # See the class docstring — a subset of dx_count/total_km specific to
    # `baseline_year`, used only for the rating/leaderboard "this year" tie.
    dx_count_this_year: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    km_this_year: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    baseline_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    runner = relationship("User", back_populates="baseline")

    def __str__(self) -> str:
        return f"{self.dx_count} DX / {self.total_runs} пробежек / {self.total_km:g} км"
