from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.attendance import AttendanceRecord
from app.models.enums import FinishStatus, ModerationStatus, ResultSource, UserRole
from app.models.event import Event
from app.models.group import Group
from app.models.result import Result
from app.models.runner_baseline import RunnerBaseline
from app.models.user import User


async def make_user(
    session: AsyncSession, email: str, role: UserRole = UserRole.runner
) -> User:
    user = User(
        first_name="Test",
        last_name=email.split("@")[0],
        email=email,
        password_hash=hash_password("password123"),
        email_verified=True,
        role=role,
    )
    session.add(user)
    await session.flush()
    return user


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
) -> AttendanceRecord:
    rec = AttendanceRecord(
        group_id=group.id,
        raw_name=f"{runner.first_name} {runner.last_name}" if runner else "Unknown",
        runner_id=runner.id if runner else None,
        finish_status=finish_status,
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


async def make_baseline(
    session: AsyncSession,
    runner: User,
    *,
    dx_count: int = 0,
    total_runs: int = 0,
    total_km: float = 0.0,
    first_run_date: date | None = None,
) -> RunnerBaseline:
    baseline = RunnerBaseline(
        runner_id=runner.id,
        dx_count=dx_count,
        total_runs=total_runs,
        total_km=total_km,
        first_run_date=first_run_date,
    )
    session.add(baseline)
    await session.flush()
    return baseline
