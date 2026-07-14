import csv
import io
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus
from app.services.guest_service import resolve_runner_for_csv_row


@dataclass
class CsvImportResult:
    created: list[AttendanceRecord]
    skipped_duplicates: int
    skipped_empty: int
    auto_matched: int
    guests_created: int
    guests_reused: int
    merged_redirects: int

    @property
    def created_count(self) -> int:
        return len(self.created)


def _normalize(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _is_zero(value: str | None) -> bool:
    """True when the (optional) `result` cell parses as exactly 0 — the CSV's way of
    marking someone who started but didn't finish. Blank/non-numeric cells are not
    treated as zero, so a `result` column with gaps doesn't silently mass-DNF rows."""
    if not value or not value.strip():
        return False
    try:
        return float(value.strip().replace(",", ".")) == 0
    except ValueError:
        return False


async def import_attendance_csv(
    session: AsyncSession, group_id: int, content: bytes | str
) -> CsvImportResult:
    """Parse a `;`-delimited CSV (columns: first_name, last_name required — kept
    separate rather than one full_name column so there's no guessing which word is
    the first name and which is the surname; email, phone, result optional) and
    create AttendanceRecord rows for a group, each immediately linked to an account
    — see app.services.guest_service.resolve_runner_for_csv_row for the exact
    resolution order (email match / merged-guest redirect / guest reuse by name /
    new guest). No file row is ever left unmatched: results show up in the protocol
    right away instead of sitting in a moderation queue.

    `result` is a simple finish flag, not a stored value: `0` means DNF (started,
    didn't finish), any other non-empty value means finished. Without a `result`
    column at all (older files), every row defaults to finished, as before.

    Duplicate names (first+last, case/space-insensitive) within the same group are
    skipped so re-running an import is safe and doesn't double-count runners.
    """
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    reader = csv.DictReader(io.StringIO(text), delimiter=";")

    headers = {(f or "").strip().lower() for f in reader.fieldnames or []}
    if not {"first_name", "last_name"} <= headers:
        raise ValueError("CSV must have 'first_name' and 'last_name' columns")

    # Map real header names case-insensitively.
    header_map = {(f or "").strip().lower(): f for f in reader.fieldnames or []}
    first_name_col = header_map["first_name"]
    last_name_col = header_map["last_name"]
    email_col = header_map.get("email")
    phone_col = header_map.get("phone")
    result_col = header_map.get("result")

    existing = await session.scalars(
        select(AttendanceRecord.raw_name).where(AttendanceRecord.group_id == group_id)
    )
    seen: set[str] = {_normalize(n) for n in existing}

    created: list[AttendanceRecord] = []
    skipped_duplicates = 0
    skipped_empty = 0
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
        key = _normalize(raw_name)
        if key in seen:
            skipped_duplicates += 1
            continue
        seen.add(key)

        finish_status = (
            FinishStatus.dnf
            if result_col and _is_zero(row.get(result_col))
            else FinishStatus.finished
        )
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

        record = AttendanceRecord(
            group_id=group_id,
            raw_name=raw_name,
            raw_email=raw_email,
            raw_phone=(row.get(phone_col) or "").strip() or None if phone_col else None,
            runner_id=runner.id,
            finish_status=finish_status,
        )
        session.add(record)
        created.append(record)

    await session.flush()
    return CsvImportResult(
        created=created,
        skipped_duplicates=skipped_duplicates,
        skipped_empty=skipped_empty,
        auto_matched=auto_matched,
        guests_created=guests_created,
        guests_reused=guests_reused,
        merged_redirects=merged_redirects,
    )
