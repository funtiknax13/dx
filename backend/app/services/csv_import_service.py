import csv
import io
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus
from app.models.group import Group
from app.services.guest_service import resolve_runner_for_csv_row

# Cyrillic letters that are visually identical to a Latin look-alike — an
# admin typing a tag in a Russian-language CSV (or a runner's name autofill)
# can easily produce "Х" (U+0425) instead of "X" (U+0058), which would
# otherwise silently fail to match a group's distance_code.
_CYRILLIC_TO_LATIN = str.maketrans("АВЕКМНОРСТУХ", "ABEKMHOPCTYX")


@dataclass
class CsvImportResult:
    created: list[AttendanceRecord]
    skipped_duplicates: int
    skipped_empty: int
    # Row's result cell was blank — explicitly "don't process this person".
    skipped_no_tag: int
    # Row had a tag letter, but no group in this event has a matching
    # distance_code (typo, or that group isn't tagged yet).
    skipped_unmatched_tag: int
    auto_matched: int
    guests_created: int
    guests_reused: int
    merged_redirects: int
    # True when no group in the event had a distance_code at all, so every
    # non-empty row was routed to the event's first group regardless of tag.
    fallback_used: bool

    @property
    def created_count(self) -> int:
        return len(self.created)


def _normalize(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _normalize_tag(value: str) -> str:
    return value.strip().upper().translate(_CYRILLIC_TO_LATIN)


def _parse_tag(raw: str) -> tuple[str, FinishStatus] | None:
    """"X" -> ("X", finished); "Xn" -> ("X", dnf); "" -> None (skip the row)."""
    value = _normalize_tag(raw)
    if not value:
        return None
    if len(value) > 1 and value.endswith("N"):
        return value[:-1], FinishStatus.dnf
    return value, FinishStatus.finished


async def import_attendance_csv(
    session: AsyncSession, event_id: int, content: bytes | str
) -> CsvImportResult:
    """Parse a `;`-delimited CSV for a whole event at once (columns: first_name,
    last_name, result required; email, phone optional) and create AttendanceRecord
    rows, each immediately linked to an account — see
    app.services.guest_service.resolve_runner_for_csv_row for the exact resolution
    order (email match / merged-guest redirect / guest reuse by name / new guest).

    `result` now does double duty as the routing tag: its first letter (Cyrillic
    look-alikes normalized to Latin) is matched against the first letter of each
    group's distance_code to pick which group the row belongs to — e.g. "X" or
    "Xn" routes to a group tagged "X-33". A trailing "n" means DNF, otherwise
    finished. An empty cell means the row is skipped outright (not imported at
    all) — this is how an admin excludes people from a shared results file.

    If a tag letter doesn't match any group's distance_code, the row is skipped
    and counted separately (skipped_unmatched_tag) rather than guessed at. If
    *no* group in the event has a distance_code set, every non-empty row is
    dropped into the event's first group (lowest id) instead — there's nothing
    to route by. When several groups share the same distance_code (pace
    subgroups sharing one merged protocol — see Group.distance_code), the tag
    resolves to the lowest-id group among them; which physical group backs the
    record doesn't matter since their protocols already display as one.

    Duplicate names (first+last, case/space-insensitive) within the same
    destination group are skipped so re-running an import is safe.
    """
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    reader = csv.DictReader(io.StringIO(text), delimiter=";")

    headers = {(f or "").strip().lower() for f in reader.fieldnames or []}
    if not {"first_name", "last_name", "result"} <= headers:
        raise ValueError("CSV must have 'first_name', 'last_name' and 'result' columns")

    header_map = {(f or "").strip().lower(): f for f in reader.fieldnames or []}
    first_name_col = header_map["first_name"]
    last_name_col = header_map["last_name"]
    result_col = header_map["result"]
    email_col = header_map.get("email")
    phone_col = header_map.get("phone")

    groups = list(
        await session.scalars(select(Group).where(Group.event_id == event_id).order_by(Group.id))
    )
    if not groups:
        raise ValueError("Event has no groups to import into")

    tag_map: dict[str, Group] = {}
    for g in groups:
        if not g.distance_code:
            continue
        letter = _normalize_tag(g.distance_code)[:1]
        if letter and letter not in tag_map:
            tag_map[letter] = g
    fallback_group = groups[0]
    fallback_used = not tag_map

    existing_rows = await session.execute(
        select(AttendanceRecord.group_id, AttendanceRecord.raw_name).where(
            AttendanceRecord.group_id.in_([g.id for g in groups])
        )
    )
    seen_by_group: dict[int, set[str]] = defaultdict(set)
    for group_id, name in existing_rows:
        seen_by_group[group_id].add(_normalize(name))

    created: list[AttendanceRecord] = []
    skipped_duplicates = 0
    skipped_empty = 0
    skipped_no_tag = 0
    skipped_unmatched_tag = 0
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

        parsed = _parse_tag(row.get(result_col) or "")
        if parsed is None:
            skipped_no_tag += 1
            continue
        letter, finish_status = parsed

        group: Group | None = fallback_group if fallback_used else tag_map.get(letter)
        if group is None:
            skipped_unmatched_tag += 1
            continue

        seen = seen_by_group[group.id]
        key = _normalize(raw_name)
        if key in seen:
            skipped_duplicates += 1
            continue
        seen.add(key)

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
            group_id=group.id,
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
        skipped_no_tag=skipped_no_tag,
        skipped_unmatched_tag=skipped_unmatched_tag,
        auto_matched=auto_matched,
        guests_created=guests_created,
        guests_reused=guests_reused,
        merged_redirects=merged_redirects,
        fallback_used=fallback_used,
    )
