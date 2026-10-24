from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.attendance import AttendanceRecord
from app.models.contest import Contest, ContestField
from app.models.enums import (
    ContestFieldType,
    FinishStatus,
    Gender,
    ModerationStatus,
    PriorExperience,
    ResultSource,
    StaffPermission,
    UserRole,
)
from app.models.event import Event
from app.models.group import Group
from app.models.result import Result
from app.models.runner_baseline import RunnerBaseline
from app.models.user import User
from app.services.permissions_service import set_permissions


async def make_user(
    session: AsyncSession,
    email: str,
    role: UserRole = UserRole.runner,
    *,
    complete_profile: bool = True,
) -> User:
    """A "normal" test user has a fully complete profile by default (see
    profile_completeness_service) so existing tests that don't care about
    that gate aren't affected by it — pass complete_profile=False for tests
    that specifically exercise the gate/locked-state behavior."""
    user = User(
        first_name="Test",
        last_name=email.split("@")[0],
        email=email,
        password_hash=hash_password("password123"),
        email_verified=True,
        role=role,
    )
    if complete_profile:
        user.birthday = date(1990, 1, 1)
        user.avatar = "/media/avatars/test.jpg"
        user.city = "Чебоксары"
        user.gender = Gender.female
        user.phone = "+79990000000"
        user.running_club = ""  # "" = explicitly "not in a club", still counts as answered
        user.prior_experience = PriorExperience.multiple
    session.add(user)
    await session.flush()
    return user


async def make_organizer(session: AsyncSession, email: str) -> User:
    """An organizer with StaffPermission.events already granted — the common
    case for tests exercising event/group admin-tools or REST routes, which
    otherwise all need an explicit grant now that "create events" is
    delegable rather than an unconditional organizer baseline (every
    *existing* organizer gets backfilled with it in the introducing
    migration; a fresh test fixture needs the same thing done by hand)."""
    org = await make_user(session, email, UserRole.organizer)
    await set_permissions(session, org, {StaffPermission.events}, granted_by=org)
    return org


async def make_event_group(
    session: AsyncSession, organizer: User, target_km: float = 10.0
) -> tuple[Event, Group]:
    event = Event(title="DX #1", date=date(2026, 5, 1), created_by=organizer.id)
    session.add(event)
    await session.flush()
    group = Group(
        event_id=event.id,
        location="City",
        name="X-10",
        target_distance_km=target_km,
        start_time=datetime(2026, 5, 1, 8, 0, tzinfo=UTC),
    )
    session.add(group)
    await session.flush()
    return event, group


async def make_attendance_with_result(
    session: AsyncSession,
    group: Group,
    runner: User | None,
    *,
    finish_status: FinishStatus,
    moderation: ModerationStatus,
    self_reported: bool = False,
) -> AttendanceRecord:
    rec = AttendanceRecord(
        group_id=group.id,
        raw_name=f"{runner.first_name} {runner.last_name}" if runner else "Unknown",
        runner_id=runner.id if runner else None,
        finish_status=finish_status,
        self_reported=self_reported,
    )
    session.add(rec)
    await session.flush()
    result = Result(
        attendance_record_id=rec.id,
        distance_km=group.target_distance_km,
        duration_seconds=3000,
        pace_seconds_per_km=300.0,
        source=ResultSource.file,
        finish_status=finish_status,
        status=moderation,
    )
    session.add(result)
    await session.flush()
    return rec


async def make_contest(
    session: AsyncSession,
    organizer: User,
    *,
    is_published: bool = False,
    submissions_open_at: datetime | None = None,
    submissions_close_at: datetime | None = None,
    voting_open_at: datetime | None = None,
    voting_close_at: datetime | None = None,
    votes_visible_live: bool = False,
    max_entries_per_runner: int | None = None,
) -> Contest:
    contest = Contest(
        title="DX маршруты",
        description="Конкурс маршрутов",
        created_by=organizer.id,
        is_published=is_published,
        submissions_open_at=submissions_open_at,
        submissions_close_at=submissions_close_at,
        voting_open_at=voting_open_at,
        voting_close_at=voting_close_at,
        votes_visible_live=votes_visible_live,
        max_entries_per_runner=max_entries_per_runner,
    )
    session.add(contest)
    await session.flush()
    return contest


async def add_contest_field(
    session: AsyncSession,
    contest: Contest,
    *,
    position: int = 0,
    label: str = "Ссылка на маршрут",
    field_type: ContestFieldType = ContestFieldType.url,
    required: bool = True,
    visible_to_voters: bool = True,
    options: list[str] | None = None,
) -> ContestField:
    field = ContestField(
        contest_id=contest.id,
        position=position,
        label=label,
        field_type=field_type,
        required=required,
        visible_to_voters=visible_to_voters,
        options=options,
    )
    session.add(field)
    await session.flush()
    return field


async def make_baseline(
    session: AsyncSession,
    runner: User,
    *,
    dx_count: int = 0,
    total_runs: int = 0,
    total_km: float = 0.0,
    first_run_date: date | None = None,
    dx_count_this_year: int = 0,
    km_this_year: float = 0.0,
    baseline_year: int | None = None,
) -> RunnerBaseline:
    baseline = RunnerBaseline(
        runner_id=runner.id,
        dx_count=dx_count,
        total_runs=total_runs,
        total_km=total_km,
        first_run_date=first_run_date,
        dx_count_this_year=dx_count_this_year,
        km_this_year=km_this_year,
        baseline_year=baseline_year,
    )
    session.add(baseline)
    await session.flush()
    return baseline
