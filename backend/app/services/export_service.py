"""Row-building queries behind /admin-tools/reports — kept separate from
app.api.groups.protocol(), which serves the public, viewer-scoped JSON
protocol: an admin/organizer export has no reason to hide an unapproved
self-report (the whole point is to see everything, labelled), so it's a
simpler, unfiltered query rather than a reuse of that endpoint's visibility
rules. app.services.xlsx_service turns these rows into actual workbooks."""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.timezone import now_msk
from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, ModerationStatus
from app.models.event import Event
from app.models.group import Group
from app.models.result import Result

_MODERATION_LABELS = {
    ModerationStatus.approved: "подтверждён",
    ModerationStatus.pending: "на проверке",
    ModerationStatus.rejected: "отклонён",
}


def _moderation_label(result: Result | None) -> str:
    return _MODERATION_LABELS[result.status] if result is not None else "—"


def _display_name(rec: AttendanceRecord) -> str:
    return f"{rec.runner.first_name} {rec.runner.last_name}" if rec.runner else rec.raw_name


def _name_key(rec: AttendanceRecord) -> tuple[str, str]:
    if rec.runner:
        return (rec.runner.last_name.lower(), rec.runner.first_name.lower())
    return (rec.raw_name.strip().lower(), "")


@dataclass
class ProtocolRow:
    family_label: str
    subgroup_name: str
    rank: int | None
    name: str
    finish_status_label: str
    moderation_label: str
    distance_km: float | None
    duration_seconds: int | None
    pace_seconds_per_km: float | None


async def build_event_protocol(session: AsyncSession, event: Event) -> list[ProtocolRow]:
    """Every attendance record for the event, grouped by distance family
    (groups sharing `distance_code` merge into one ranked block — same unit
    the public protocol ranks within, see app.api.groups.protocol) and
    ordered: ranked finishers (approved + finished, by duration) first, then
    DNF, then anything without an approved finish yet — by name within each
    bucket. Nothing is excluded; the moderation column says why a row isn't
    ranked rather than hiding it."""
    groups = list(
        await session.scalars(
            select(Group)
            .where(Group.event_id == event.id)
            .options(
                selectinload(Group.attendance_records).options(
                    selectinload(AttendanceRecord.result),
                    selectinload(AttendanceRecord.runner),
                )
            )
            .order_by(Group.id)
        )
    )
    families: dict[str, list[Group]] = {}
    for g in groups:
        key = g.distance_code or f"_standalone_{g.id}"
        families.setdefault(key, []).append(g)

    rows: list[ProtocolRow] = []
    for family_groups in families.values():
        lead = family_groups[0]
        label = lead.distance_code or lead.name
        if lead.location:
            label = f"{label} · {lead.location}"
        records = [rec for g in family_groups for rec in g.attendance_records]

        finishers = [
            r
            for r in records
            if r.result is not None
            and r.result.status == ModerationStatus.approved
            and r.finish_status == FinishStatus.finished
        ]
        finishers.sort(key=lambda r: (r.result.duration_seconds, *_name_key(r)))

        dnf = [r for r in records if r.finish_status == FinishStatus.dnf]
        dnf.sort(key=_name_key)

        others = [r for r in records if r not in finishers and r not in dnf]
        others.sort(key=_name_key)

        for rank, rec in enumerate(finishers, start=1):
            res = rec.result
            assert res is not None
            rows.append(
                ProtocolRow(
                    family_label=label,
                    subgroup_name=rec.group.name,
                    rank=rank,
                    name=_display_name(rec),
                    finish_status_label="финишировал",
                    moderation_label=_moderation_label(res),
                    distance_km=lead.target_distance_km,
                    duration_seconds=res.duration_seconds,
                    pace_seconds_per_km=res.duration_seconds / lead.target_distance_km
                    if lead.target_distance_km
                    else None,
                )
            )
        for rec in dnf:
            res = rec.result
            rows.append(
                ProtocolRow(
                    family_label=label,
                    subgroup_name=rec.group.name,
                    rank=None,
                    name=_display_name(rec),
                    finish_status_label="DNF",
                    moderation_label=_moderation_label(res),
                    distance_km=res.distance_km if res else None,
                    duration_seconds=res.duration_seconds if res else None,
                    pace_seconds_per_km=res.pace_seconds_per_km if res else None,
                )
            )
        for rec in others:
            res = rec.result
            rows.append(
                ProtocolRow(
                    family_label=label,
                    subgroup_name=rec.group.name,
                    rank=None,
                    name=_display_name(rec),
                    finish_status_label="финишировал",
                    moderation_label=_moderation_label(res),
                    distance_km=res.distance_km if res else None,
                    duration_seconds=res.duration_seconds if res else None,
                    pace_seconds_per_km=res.pace_seconds_per_km if res else None,
                )
            )
    return rows


@dataclass
class ResultListRow:
    event_date: date
    event_title: str
    group_name: str
    name: str
    finish_status_label: str
    moderation_label: str
    distance_km: float | None
    duration_seconds: int | None
    pace_seconds_per_km: float | None
    source_label: str
    created_at: datetime


_SOURCE_LABELS = {"file": "файл", "manual": "ручной ввод"}


async def build_results_list(
    session: AsyncSession,
    *,
    created_by: int | None = None,
    event_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[ResultListRow]:
    """Flat list of every attendance record in range, one row each — for
    pulling into a spreadsheet for outside analysis, not for reading as a
    protocol (see build_event_protocol for that). `created_by` scopes to one
    organizer's own events; omit it for the admin's unrestricted view."""
    stmt = (
        select(AttendanceRecord)
        .join(Group, Group.id == AttendanceRecord.group_id)
        .join(Event, Event.id == Group.event_id)
        .options(
            selectinload(AttendanceRecord.result),
            selectinload(AttendanceRecord.runner),
            selectinload(AttendanceRecord.group).selectinload(Group.event),
        )
        .order_by(Event.date.desc(), Group.id, AttendanceRecord.id)
    )
    if created_by is not None:
        stmt = stmt.where(Event.created_by == created_by)
    if event_id is not None:
        stmt = stmt.where(Event.id == event_id)
    if date_from is not None:
        stmt = stmt.where(Event.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Event.date <= date_to)

    records = list(await session.scalars(stmt))
    rows: list[ResultListRow] = []
    for rec in records:
        res = rec.result
        group = rec.group
        event = group.event
        rows.append(
            ResultListRow(
                event_date=event.date,
                event_title=event.title,
                group_name=group.name,
                name=_display_name(rec),
                finish_status_label=(
                    "DNF" if rec.finish_status == FinishStatus.dnf else "финишировал"
                ),
                moderation_label=_moderation_label(res),
                distance_km=res.distance_km if res else None,
                duration_seconds=res.duration_seconds if res else None,
                pace_seconds_per_km=res.pace_seconds_per_km if res else None,
                source_label=_SOURCE_LABELS[res.source.value] if res else "—",
                created_at=rec.created_at,
            )
        )
    return rows


@dataclass
class SummaryStats:
    events_count: int
    groups_count: int
    attendance_count: int
    finished_count: int
    dnf_count: int
    unique_runners: int
    total_km: float
    generated_at: datetime


async def build_summary(session: AsyncSession, *, created_by: int | None = None) -> SummaryStats:
    """Raw operational totals — every tracked attendance record regardless of
    moderation status, not the stricter counts_toward_rating definition the
    community rating uses (see rating_service.counts_toward_rating). This is
    "how much happened", not "what counts for ranking"."""
    events_stmt = select(Event)
    if created_by is not None:
        events_stmt = events_stmt.where(Event.created_by == created_by)
    events_count = len(list(await session.scalars(events_stmt.with_only_columns(Event.id))))

    groups_stmt = select(Group).join(Event, Event.id == Group.event_id)
    attendance_stmt = (
        select(AttendanceRecord)
        .join(Group, Group.id == AttendanceRecord.group_id)
        .join(Event, Event.id == Group.event_id)
    )
    if created_by is not None:
        groups_stmt = groups_stmt.where(Event.created_by == created_by)
        attendance_stmt = attendance_stmt.where(Event.created_by == created_by)

    groups_count = len(list(await session.scalars(groups_stmt.with_only_columns(Group.id))))
    records = list(
        await session.scalars(attendance_stmt.options(selectinload(AttendanceRecord.group)))
    )
    finished = [r for r in records if r.finish_status == FinishStatus.finished]
    dnf = [r for r in records if r.finish_status == FinishStatus.dnf]
    unique_runners = len({r.runner_id for r in records if r.runner_id is not None})
    total_km = sum(r.group.target_distance_km for r in finished)

    return SummaryStats(
        events_count=events_count,
        groups_count=groups_count,
        attendance_count=len(records),
        finished_count=len(finished),
        dnf_count=len(dnf),
        unique_runners=unique_runners,
        total_km=total_km,
        generated_at=now_msk(),
    )
