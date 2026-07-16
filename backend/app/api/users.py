from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.core.security import hash_password, verify_password
from app.models.attendance import AttendanceRecord
from app.models.event import Event
from app.models.group import Group
from app.models.signup import Signup
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.common import Page
from app.schemas.user import (
    AccountDeleteRequest,
    AccountExport,
    AccountExportHistoryItem,
    AccountExportSignup,
    AchievementItem,
    ParticipationHistoryItem,
    PasswordChangeRequest,
    PublicProfile,
    UserMe,
    UserUpdate,
)
from app.services.achievement_service import compute_achievements
from app.services.media_service import (
    FileTooLargeError,
    InvalidFileTypeError,
    delete_media,
    save_image,
)
from app.services.rating_service import runner_finished_count
from app.services.stats_service import compute_profile_stats

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMe)
async def get_me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserMe)
async def update_me(payload: UserUpdate, user: CurrentUser, session: SessionDep) -> User:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/me/password", response_model=MessageResponse)
async def change_password(
    payload: PasswordChangeRequest, user: CurrentUser, session: SessionDep
) -> MessageResponse:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    await session.commit()
    return MessageResponse(detail="Password updated")


@router.post("/me/avatar", response_model=UserMe)
async def upload_avatar(user: CurrentUser, session: SessionDep, file: UploadFile) -> User:
    try:
        path = await save_image(file, "avatars")
    except (FileTooLargeError, InvalidFileTypeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    delete_media(user.avatar)
    user.avatar = path
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/me/export", response_model=AccountExport)
async def export_me(user: CurrentUser, session: SessionDep) -> AccountExport:
    records = await session.scalars(
        select(AttendanceRecord)
        .where(AttendanceRecord.runner_id == user.id)
        .options(
            selectinload(AttendanceRecord.group).selectinload(Group.event),
            selectinload(AttendanceRecord.result),
        )
        .order_by(AttendanceRecord.id.desc())
    )
    history: list[AccountExportHistoryItem] = []
    for rec in records:
        group: Group = rec.group
        event: Event = group.event
        res = rec.result
        history.append(
            AccountExportHistoryItem(
                attendance_id=rec.id,
                group_id=group.id,
                group_name=group.name,
                event_id=event.id,
                event_title=event.title,
                event_date=event.date,
                finish_status=rec.finish_status.value,
                distance_km=res.distance_km if res else None,
                duration_seconds=res.duration_seconds if res else None,
                pace_seconds_per_km=res.pace_seconds_per_km if res else None,
                moderation_status=res.status.value if res else None,
            )
        )

    signup_rows = await session.scalars(
        select(Signup)
        .where(Signup.runner_id == user.id)
        .options(selectinload(Signup.group).selectinload(Group.event))
    )
    signups = [
        AccountExportSignup(
            signup_id=s.id,
            group_id=s.group.id,
            group_name=s.group.name,
            event_id=s.group.event.id,
            event_title=s.group.event.title,
            event_date=s.group.event.date,
        )
        for s in signup_rows
    ]

    return AccountExport(
        profile=UserMe.model_validate(user),
        account_created_at=user.created_at,
        privacy_accepted_at=user.privacy_accepted_at,
        history=history,
        signups=signups,
    )


@router.delete("/me", response_model=MessageResponse)
async def delete_me(
    payload: AccountDeleteRequest, user: CurrentUser, session: SessionDep
) -> MessageResponse:
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неверный пароль")

    owned_events = await session.scalar(
        select(func.count(Event.id)).where(Event.created_by == user.id)
    )
    if owned_events:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "У вас есть созданные события — обратитесь к администратору, "
            "чтобы передать их другому организатору перед удалением аккаунта",
        )

    # Scrub the contact info frozen in past attendance rows before detaching
    # them — the finish/protocol history itself is kept (same as a guest
    # merge: identity is removed, the sporting record isn't).
    await session.execute(
        update(AttendanceRecord)
        .where(AttendanceRecord.runner_id == user.id)
        .values(raw_email=None, raw_phone=None)
    )

    if user.avatar:
        delete_media(user.avatar)

    await session.delete(user)
    await session.commit()
    return MessageResponse(detail="Аккаунт удалён")


@router.get("/{user_id}/history", response_model=Page[ParticipationHistoryItem])
async def user_history(
    user_id: int,
    session: SessionDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[ParticipationHistoryItem]:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    base = select(AttendanceRecord).where(AttendanceRecord.runner_id == user_id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    records = await session.scalars(
        base.options(
            selectinload(AttendanceRecord.group).selectinload(Group.event),
            selectinload(AttendanceRecord.result),
        )
        .order_by(AttendanceRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    items: list[ParticipationHistoryItem] = []
    for rec in records:
        group: Group = rec.group
        event: Event = group.event
        items.append(
            ParticipationHistoryItem(
                attendance_id=rec.id,
                group_id=group.id,
                group_name=group.name,
                event_id=event.id,
                event_title=event.title,
                event_date=event.date,
                finish_status=rec.finish_status.value,
                has_result=rec.result is not None,
            )
        )
    return Page(items=items, total=total or 0, page=page, page_size=page_size)


@router.get("/{user_id}", response_model=PublicProfile)
async def public_profile(user_id: int, session: SessionDep) -> PublicProfile:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    rating = await runner_finished_count(session, user_id, period="all")
    stats = await compute_profile_stats(session, user_id)
    achievements = await compute_achievements(session, user_id)
    return PublicProfile(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        avatar=user.avatar,
        is_guest=user.is_guest,
        registered_at=None if user.is_guest else user.created_at,
        rating=rating,
        first_run_date=stats.first_run_date,
        total_runs_count=stats.total_runs_count,
        dnf_count=stats.dnf_count,
        full_dx_km=stats.full_dx_km,
        current_streak=stats.current_streak,
        longest_streak=stats.longest_streak,
        achievements=[
            AchievementItem(
                threshold=a.threshold,
                reached=a.reached,
                reached_at=a.reached_at,
                event_id=a.event_id,
                event_title=a.event_title,
            )
            for a in achievements
        ],
    )
