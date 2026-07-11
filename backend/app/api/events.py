from fastapi import APIRouter, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import OrganizerUser, SessionDep
from app.models.enums import UserRole
from app.models.event import Event, EventPhoto
from app.models.user import User
from app.schemas.event import (
    EventCreate,
    EventOut,
    EventPhotoOut,
    EventUpdate,
)
from app.services.media_service import (
    FileTooLargeError,
    InvalidFileTypeError,
    delete_media,
    save_image,
    save_image_with_thumbnail,
)

router = APIRouter(prefix="/events", tags=["events"])


async def _get_event_or_404(session: SessionDep, event_id: int) -> Event:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    return event


def _assert_can_manage(event: Event, user: User) -> None:
    """Organizer may manage only their own events; admin may manage all."""
    if user.role == UserRole.admin:
        return
    if event.created_by != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not manage this event")


@router.get("", response_model=list[EventOut])
async def list_events(session: SessionDep) -> list[Event]:
    events = await session.scalars(select(Event).order_by(Event.date.desc()))
    return list(events)


@router.get("/{event_id}", response_model=EventOut)
async def get_event(event_id: int, session: SessionDep) -> Event:
    return await _get_event_or_404(session, event_id)


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: EventCreate, user: OrganizerUser, session: SessionDep
) -> Event:
    event = Event(**payload.model_dump(), created_by=user.id)
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


@router.patch("/{event_id}", response_model=EventOut)
async def update_event(
    event_id: int, payload: EventUpdate, user: OrganizerUser, session: SessionDep
) -> Event:
    event = await _get_event_or_404(session, event_id)
    _assert_can_manage(event, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    await session.commit()
    await session.refresh(event)
    return event


@router.post("/{event_id}/cover", response_model=EventOut)
async def upload_cover(
    event_id: int, user: OrganizerUser, session: SessionDep, file: UploadFile
) -> Event:
    event = await _get_event_or_404(session, event_id)
    _assert_can_manage(event, user)
    try:
        path = await save_image(file, "covers")
    except (FileTooLargeError, InvalidFileTypeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    delete_media(event.cover_image)
    event.cover_image = path
    await session.commit()
    await session.refresh(event)
    return event


@router.get("/{event_id}/photos", response_model=list[EventPhotoOut])
async def list_photos(event_id: int, session: SessionDep) -> list[EventPhoto]:
    await _get_event_or_404(session, event_id)
    photos = await session.scalars(
        select(EventPhoto).where(EventPhoto.event_id == event_id).order_by(EventPhoto.id.desc())
    )
    return list(photos)


@router.post(
    "/{event_id}/photos", response_model=list[EventPhotoOut], status_code=status.HTTP_201_CREATED
)
async def upload_photos(
    event_id: int, user: OrganizerUser, session: SessionDep, files: list[UploadFile]
) -> list[EventPhoto]:
    event = await _get_event_or_404(session, event_id)
    _assert_can_manage(event, user)
    photos = []
    for file in files:
        try:
            path, thumb_path = await save_image_with_thumbnail(file, "photos")
        except (FileTooLargeError, InvalidFileTypeError) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{file.filename}: {exc}") from exc
        photos.append(
            EventPhoto(event_id=event.id, image=path, thumbnail=thumb_path, uploaded_by=user.id)
        )
    session.add_all(photos)
    await session.commit()
    for photo in photos:
        await session.refresh(photo)
    return photos
