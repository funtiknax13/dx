import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.city import City
from app.models.enums import Gender
from app.models.runner_baseline import RunnerBaseline
from app.services.guest_service import resolve_runner_for_csv_row


@dataclass
class BaselineImportResult:
    created: int
    updated: int
    skipped_empty: int
    skipped_invalid_number: int
    skipped_invalid_date: int
    auto_matched: int
    guests_created: int
    guests_reused: int
    merged_redirects: int
    city_linked: int = 0
    city_unmatched: int = 0
    unmatched_cities: list[str] = field(default_factory=list)
    gender_linked: int = 0
    gender_unmatched: int = 0


async def _match_city(session: AsyncSession, raw: str) -> City | None:
    """Find a City by exact (case-insensitive) name — Russian or Latin. When a
    name resolves to several places (GeoNames has many namesakes), take the most
    populous, which is almost always the intended one for our runners."""
    norm = raw.strip().lower()
    if not norm:
        return None
    city: City | None = await session.scalar(
        select(City)
        .where((City.search_name == norm) | (City.search_ascii == norm))
        .order_by(City.population.desc())
    )
    return city


_GENDER_ALIASES = {
    "male": Gender.male,
    "m": Gender.male,
    "м": Gender.male,
    "муж": Gender.male,
    "мужской": Gender.male,
    "female": Gender.female,
    "f": Gender.female,
    "ж": Gender.female,
    "жен": Gender.female,
    "женский": Gender.female,
}


def _parse_gender(raw: str | None) -> Gender | None:
    """None both for a blank cell and for an unrecognized value — the caller
    tells the two apart itself (blank isn't counted as unmatched, a typo is)."""
    return _GENDER_ALIASES.get((raw or "").strip().lower())


def _parse_int(raw: str | None) -> int | None:
    value = (raw or "").strip()
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        return None


def _parse_float(raw: str | None) -> float | None:
    value = (raw or "").strip()
    if not value:
        return 0.0
    try:
        return float(value.replace(",", "."))  # Russian-locale exports use a comma
    except ValueError:
        return None


def _parse_nullable_int(raw: str | None) -> tuple[int | None, bool]:
    """(value, is_valid) — blank is valid and means "unset" (None), unlike
    _parse_int where blank means 0. Used for baseline_year, which has no
    sensible zero default."""
    value = (raw or "").strip()
    if not value:
        return None, True
    try:
        return int(value), True
    except ValueError:
        return None, False


def _parse_date(raw: str | None) -> tuple[date | None, bool]:
    """(value, is_valid) — blank is valid (nothing provided). Accepts ISO
    (YYYY-MM-DD) and Russian-locale (DD.MM.YYYY) — the latter is what Excel
    produces by default under a Russian locale, which is how this column is
    actually filled in practice."""
    value = (raw or "").strip()
    if not value:
        return None, True
    try:
        return date.fromisoformat(value), True
    except ValueError:
        pass
    try:
        return datetime.strptime(value, "%d.%m.%Y").date(), True
    except ValueError:
        return None, False


async def import_baseline_csv(session: AsyncSession, content: bytes | str) -> BaselineImportResult:
    """Parse a `;`-delimited CSV of admin-entered carry-over stats (columns:
    first_name, last_name required; dx_count, total_runs, total_km,
    first_run_date (YYYY-MM-DD or DD.MM.YYYY — see _parse_date), dx_count_this_year, km_this_year,
    baseline_year, email, city, gender optional, missing/blank numbers default to 0 except
    baseline_year which defaults to unset/None) and upsert one RunnerBaseline
    per row. dx_count_this_year/km_this_year are a *subset* of dx_count/
    total_km (see RunnerBaseline), not additive — they only feed the "this
    year" rating/leaderboard bucket while baseline_year is the current
    calendar year.

    Runner resolution reuses the exact same rule as attendance CSV import —
    see app.services.guest_service.resolve_runner_for_csv_row (email match /
    merged-guest redirect / guest reuse by name / new guest) — so a starting
    balance set for someone who hasn't registered yet still lands on a guest
    profile, ready to be claimed and merged like any other guest data.

    Re-running the same file is safe: a row overwrites (not adds to) that
    runner's existing baseline, rather than accumulating duplicates.
    """
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    reader = csv.DictReader(io.StringIO(text), delimiter=";")

    headers = {(f or "").strip().lower() for f in reader.fieldnames or []}
    if not {"first_name", "last_name"} <= headers:
        raise ValueError("CSV must have 'first_name' and 'last_name' columns")

    header_map = {(f or "").strip().lower(): f for f in reader.fieldnames or []}
    first_name_col = header_map["first_name"]
    last_name_col = header_map["last_name"]
    dx_count_col = header_map.get("dx_count")
    total_runs_col = header_map.get("total_runs")
    total_km_col = header_map.get("total_km")
    first_run_date_col = header_map.get("first_run_date")
    dx_count_this_year_col = header_map.get("dx_count_this_year")
    km_this_year_col = header_map.get("km_this_year")
    baseline_year_col = header_map.get("baseline_year")
    email_col = header_map.get("email")
    city_col = header_map.get("city")
    gender_col = header_map.get("gender")

    created = 0
    updated = 0
    skipped_empty = 0
    skipped_invalid_number = 0
    skipped_invalid_date = 0
    auto_matched = 0
    guests_created = 0
    guests_reused = 0
    merged_redirects = 0
    city_linked = 0
    city_unmatched = 0
    unmatched_cities: list[str] = []
    gender_linked = 0
    gender_unmatched = 0

    for row in reader:
        first_name = (row.get(first_name_col) or "").strip()
        last_name = (row.get(last_name_col) or "").strip()
        raw_name = f"{first_name} {last_name}".strip()
        if not raw_name:
            skipped_empty += 1
            continue

        dx_count = _parse_int(row.get(dx_count_col) if dx_count_col else None)
        total_runs = _parse_int(row.get(total_runs_col) if total_runs_col else None)
        total_km = _parse_float(row.get(total_km_col) if total_km_col else None)
        first_run_date, first_run_date_valid = _parse_date(
            row.get(first_run_date_col) if first_run_date_col else None
        )
        dx_count_this_year = _parse_int(
            row.get(dx_count_this_year_col) if dx_count_this_year_col else None
        )
        km_this_year = _parse_float(row.get(km_this_year_col) if km_this_year_col else None)
        baseline_year, baseline_year_valid = _parse_nullable_int(
            row.get(baseline_year_col) if baseline_year_col else None
        )
        if not first_run_date_valid:
            # Checked separately from the numeric fields below — a bad date
            # isn't a bad number, and conflating them in one counter is
            # exactly what made this failure mode hard to diagnose before.
            skipped_invalid_date += 1
            continue
        if (
            dx_count is None
            or total_runs is None
            or total_km is None
            or dx_count_this_year is None
            or km_this_year is None
            or not baseline_year_valid
        ):
            skipped_invalid_number += 1
            continue

        raw_email = (row.get(email_col) or "").strip() or None if email_col else None
        runner, resolution = await resolve_runner_for_csv_row(session, raw_name, raw_email)
        if resolution == "email_match":
            auto_matched += 1
        elif resolution == "merge_redirect":
            merged_redirects += 1
        elif resolution == "guest_reused":
            guests_reused += 1
        else:
            guests_created += 1

        # Optional city column: match to the canonical dictionary and link it,
        # without clobbering a city the runner already chose themselves.
        if city_col:
            city_raw = (row.get(city_col) or "").strip()
            if city_raw:
                city = await _match_city(session, city_raw)
                if city is not None:
                    if runner.city_id is None:
                        runner.city_id = city.id
                        runner.city = city.name
                    city_linked += 1
                else:
                    city_unmatched += 1
                    if city_raw not in unmatched_cities:
                        unmatched_cities.append(city_raw)

        # Optional gender column: same non-clobbering rule as city — this is
        # what feeds the gender-split rating for runners who never filled it
        # in themselves (guest accounts can't, and plenty of registered ones
        # skip an optional field).
        if gender_col:
            gender_raw = (row.get(gender_col) or "").strip()
            if gender_raw:
                gender = _parse_gender(gender_raw)
                if gender is not None:
                    if runner.gender is None:
                        runner.gender = gender
                    gender_linked += 1
                else:
                    gender_unmatched += 1

        baseline = await session.scalar(
            select(RunnerBaseline).where(RunnerBaseline.runner_id == runner.id)
        )
        if baseline is None:
            session.add(
                RunnerBaseline(
                    runner_id=runner.id,
                    dx_count=dx_count,
                    total_runs=total_runs,
                    total_km=total_km,
                    first_run_date=first_run_date,
                    dx_count_this_year=dx_count_this_year,
                    km_this_year=km_this_year,
                    baseline_year=baseline_year,
                )
            )
            created += 1
        else:
            baseline.dx_count = dx_count
            baseline.total_runs = total_runs
            baseline.total_km = total_km
            baseline.first_run_date = first_run_date
            baseline.dx_count_this_year = dx_count_this_year
            baseline.km_this_year = km_this_year
            baseline.baseline_year = baseline_year
            updated += 1

    await session.flush()
    return BaselineImportResult(
        created=created,
        updated=updated,
        skipped_empty=skipped_empty,
        skipped_invalid_number=skipped_invalid_number,
        skipped_invalid_date=skipped_invalid_date,
        auto_matched=auto_matched,
        guests_created=guests_created,
        guests_reused=guests_reused,
        merged_redirects=merged_redirects,
        city_linked=city_linked,
        city_unmatched=city_unmatched,
        unmatched_cities=unmatched_cities,
        gender_linked=gender_linked,
        gender_unmatched=gender_unmatched,
    )
