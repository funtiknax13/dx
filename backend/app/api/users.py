from fastapi import APIRouter, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.core.security import hash_password, verify_password
from app.models.attendance import AttendanceRecord
from app.models.event import Event
from app.models.group import Group
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.user import (
    ParticipationHistoryItem,
    PasswordChangeRequest,
    PublicProfile,
    UserMe,
    UserUpdate,
)
from app.services.media_service import (
    FileTooLargeError,
    InvalidFileTypeError,
    delete_media,
    save_image,
)
from app.services.rating_service import runner_finished_count

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


@router.get("/{user_id}", response_model=PublicProfile)
async def public_profile(user_id: int, session: SessionDep) -> PublicProfile:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    records = await session.scalars(
        select(AttendanceRecord)
        .where(AttendanceRecord.runner_id == user_id)
        .options(
            selectinload(AttendanceRecord.group).selectinload(Group.event),
            selectinload(AttendanceRecord.result),
        )
        .order_by(AttendanceRecord.id.desc())
    )

    history: list[ParticipationHistoryItem] = []
    for rec in records:
        group: Group = rec.group
        event: Event = group.event
        history.append(
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

    rating = await runner_finished_count(session, user_id, period="all")
    return PublicProfile(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        avatar=user.avatar,
        rating=rating,
        history=history,
    )
