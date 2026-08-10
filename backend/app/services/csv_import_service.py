import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
class EmailMismatch:
    """A row resolved to an existing account by name alone (see
    guest_service.resolve_runner_for_csv_row), but its email doesn't match any
    email already known for that account — could be two different people who
    happen to share a name, silently merged into one profile. Surfaced for
    admin review, not blocked automatically (the resolution already happened;
    this is a heads-up, not a rejection)."""

    raw_name: str
    row_email: str
    known_email: str


@dataclass
class SelfReportConflict:
    """A runner self-reported a result for one distance (see
    AttendanceRecord.self_reported) but the CSV placed them in a *different*
    distance's protocol — the two don't merge, so they'd show in both. Surfaced
    for the admin to reconcile; not resolved automatically."""

    raw_name: str
    self_reported_code: str
    csv_code: str


@dataclass
class CsvImportResult:
    created: list[AttendanceRecord]
    # Existing records (from a previous import or a runner's self-report)
    # matched by (runner, distance) and updated in place instead of duplicated.
    updated: int
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
    email_mismatches: list[EmailMismatch]
    self_report_conflicts: list[SelfReportConflict] = field(default_factory=list)

    @property
    def created_count(self) -> int:
        return len(self.created)


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


def _family_of(group: Group) -> str:
    """The shared-protocol identity of a group: groups with the same
    distance_code render as one protocol, so the normalized code is their
    common key. A group without a code stands alone (keyed by its id). Dedup
    keys on (runner, family) so a runner appears once per shared protocol —
    whether added by CSV or by their own pre-protocol upload."""
    if group.distance_code:
        code = _normalize_tag(group.distance_code)
        if code:
            return code
    return f"g{group.id}"


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

    A row that resolves to an existing account by name alone (guest_reused or
    merge_redirect) whose email doesn't match anything already on file for
    that account is *not* rejected or redirected elsewhere — the row still
    imports as usual — but is collected into `email_mismatches` for the admin
    to review, since it may mean two different people share a name.
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

    group_by_id = {g.id: g for g in groups}

    # Existing records for this event's groups, keyed by (runner, distance
    # family). A CSV row for a runner who already has a record in that family
    # (from a prior import or their own pre-protocol upload) updates it in place
    # rather than creating a duplicate — that keeps the shared protocol unified.
    existing_records = list(
        await session.scalars(
            select(AttendanceRecord)
            .where(AttendanceRecord.group_id.in_(group_by_id))
            .options(selectinload(AttendanceRecord.result))
        )
    )
    existing_by_runner_family: dict[tuple[int, str], AttendanceRecord] = {}
    self_reported_by_runner: dict[int, list[tuple[str, AttendanceRecord]]] = defaultdict(list)
    for rec in existing_records:
        if rec.runner_id is None:
            continue
        fam = _family_of(group_by_id[rec.group_id])
        existing_by_runner_family[(rec.runner_id, fam)] = rec
        if rec.self_reported:
            self_reported_by_runner[rec.runner_id].append((fam, rec))

    # Every email ever seen for each account, from past AttendanceRecords —
    # used below to flag a name-only match (guest_reused/merge_redirect) whose
    # email doesn't match anything already on file for that account. That
    # combination is the signature of two different real people who happen to
    # share a name, which resolve_runner_for_csv_row can't tell apart on its
    # own (it matches guests by name alone — see CLAUDE.md).
    known_emails: dict[int, set[str]] = defaultdict(set)
    existing_emails = await session.execute(
        select(AttendanceRecord.runner_id, AttendanceRecord.raw_email).where(
            AttendanceRecord.runner_id.is_not(None), AttendanceRecord.raw_email.is_not(None)
        )
    )
    for runner_id, email in existing_emails:
        known_emails[runner_id].add(email.strip().lower())

    created: list[AttendanceRecord] = []
    processed_keys: set[tuple[int, str]] = set()
    updated = 0
    skipped_duplicates = 0
    skipped_empty = 0
    skipped_no_tag = 0
    skipped_unmatched_tag = 0
    auto_matched = 0
    guests_created = 0
    guests_reused = 0
    merged_redirects = 0
    email_mismatches: list[EmailMismatch] = []
    self_report_conflicts: list[SelfReportConflict] = []

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
        family = _family_of(group)

        raw_email = (row.get(email_col) or "").strip() or None if email_col else None
        raw_phone = (row.get(phone_col) or "").strip() or None if phone_col else None
        runner, resolution = await resolve_runner_for_csv_row(session, raw_name, raw_email)

        key = (runner.id, family)
        if key in processed_keys:
            # Same runner + distance already handled earlier in this same file.
            skipped_duplicates += 1
            continue
        processed_keys.add(key)

        if resolution == "email_match":
            auto_matched += 1
        elif resolution == "merge_redirect":
            merged_redirects += 1
        elif resolution == "guest_reused":
            guests_reused += 1
        else:
            guests_created += 1

        if raw_email and resolution in ("guest_reused", "merge_redirect"):
            normalized_email = raw_email.strip().lower()
            prior_emails = known_emails[runner.id]
            if prior_emails and normalized_email not in prior_emails:
                email_mismatches.append(
                    EmailMismatch(
                        raw_name=raw_name,
                        row_email=raw_email,
                        known_email=next(iter(prior_emails)),
                    )
                )
        if raw_email:
            known_emails[runner.id].add(raw_email.strip().lower())

        existing = existing_by_runner_family.get(key)
        if existing is not None:
            # Merge: CSV is the source of truth for finish_status and the raw
            # fields; the runner's own uploaded Result (if any) is preserved.
            existing.raw_name = raw_name
            existing.raw_email = raw_email
            existing.raw_phone = raw_phone
            existing.finish_status = finish_status
            existing.self_reported = False
            if existing.result is not None:
                existing.result.finish_status = finish_status
            updated += 1
            continue

        # A brand-new record. If the runner self-reported a *different* distance,
        # the two protocols won't merge — flag it for the admin.
        for fam, _rec in self_reported_by_runner.get(runner.id, []):
            if fam != family:
                self_report_conflicts.append(
                    SelfReportConflict(
                        raw_name=raw_name,
                        self_reported_code=fam,
                        csv_code=family,
                    )
                )
                break

        record = AttendanceRecord(
            group_id=group.id,
            raw_name=raw_name,
            raw_email=raw_email,
            raw_phone=raw_phone,
            runner_id=runner.id,
            finish_status=finish_status,
        )
        session.add(record)
        created.append(record)
        existing_by_runner_family[key] = record

    await session.flush()
    return CsvImportResult(
        created=created,
        updated=updated,
        skipped_duplicates=skipped_duplicates,
        skipped_empty=skipped_empty,
        skipped_no_tag=skipped_no_tag,
        skipped_unmatched_tag=skipped_unmatched_tag,
        auto_matched=auto_matched,
        guests_created=guests_created,
        guests_reused=guests_reused,
        merged_redirects=merged_redirects,
        fallback_used=fallback_used,
        email_mismatches=email_mismatches,
        self_report_conflicts=self_report_conflicts,
    )
