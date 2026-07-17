import csv
import io
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.runner_baseline import RunnerBaseline
from app.services.guest_service import resolve_runner_for_csv_row


@dataclass
class BaselineImportResult:
    created: int
    updated: int
    skipped_empty: int
    skipped_invalid_number: int
    auto_matched: int
    guests_created: int
    guests_reused: int
    merged_redirects: int


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


async def import_baseline_csv(session: AsyncSession, content: bytes | str) -> BaselineImportResult:
    """Parse a `;`-delimited CSV of admin-entered carry-over stats (columns:
    first_name, last_name required; dx_count, total_runs, total_km, email
    optional, missing/blank numbers default to 0) and upsert one
    RunnerBaseline per row.

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
    email_col = header_map.get("email")

    created = 0
    updated = 0
    skipped_empty = 0
    skipped_invalid_number = 0
    auto_matched = 0
    guests_created = 0
    guests_reused = 0
    merged_redirects = 0

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
        if dx_count is None or total_runs is None or total_km is None:
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
                )
            )
            created += 1
        else:
            baseline.dx_count = dx_count
            baseline.total_runs = total_runs
            baseline.total_km = total_km
            updated += 1

    await session.flush()
    return BaselineImportResult(
        created=created,
        updated=updated,
        skipped_empty=skipped_empty,
        skipped_invalid_number=skipped_invalid_number,
        auto_matched=auto_matched,
        guests_created=guests_created,
        guests_reused=guests_reused,
        merged_redirects=merged_redirects,
    )
