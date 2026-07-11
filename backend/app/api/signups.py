from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.core.timezone import EVENT_TZ
from app.models.event import Event
from app.models.group import Group
from app.models.signup import Signup
from app.schemas.signup import (
    EventSignupState,
    GroupSignupState,
    MySignupEntry,
    SignupGroupSummary,
    SignupOut,
    SignupRoster,
    SignupRosterEntry,
)

router = APIRouter(tags=["signups"])


@router.get("/groups/{group_id}/signups/me", response_model=GroupSignupState)
async def my_signup_state(
    group_id: int, user: CurrentUser, session: SessionDep
) -> GroupSignupState:
    group = await session.get(Group, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")

    # A runner can only ever have one signup per event (see Signup's
    # uq_signup_runner_event constraint), so this single lookup tells us
    # both "am I signed up here" and "am I signed up somewhere else in this
    # event instead".
    signup = await session.scalar(
        select(Signup)
        .where(Signup.event_id == group.event_id, Signup.runner_id == user.id)
        .options(selectinload(Signup.group))
    )
    if signup is None:
        return GroupSignupState(signed_up=False)
    if signup.group_id == group_id:
        return GroupSignupState(signed_up=True, signup_id=signup.id)
    return GroupSignupState(
        signed_up=False,
        other_group=SignupGroupSummary(group_id=signup.group_id, group_name=signup.group.name),
    )


@router.get("/events/{event_id}/signups/me", response_model=EventSignupState)
async def my_event_signup_state(
    event_id: int, user: CurrentUser, session: SessionDep
) -> EventSignupState:
    signup = await session.scalar(
        select(Signup)
        .where(Signup.event_id == event_id, Signup.runner_id == user.id)
        .options(selectinload(Signup.group))
    )
    if signup is None:
        return EventSignupState(signed_up=False)
    return EventSignupState(
        signed_up=True, group_id=signup.group_id, group_name=signup.group.name
    )


@router.get("/users/me/signups", response_model=list[MySignupEntry])
async def my_signups(user: CurrentUser, session: SessionDep) -> list[MySignupEntry]:
    """Upcoming events the runner has signed up for — past ones drop off since
    the protocol (actual attendance) is what matters once the event happens."""
    today = datetime.now(EVENT_TZ).date()
    rows = await session.scalars(
        select(Signup)
        .join(Event, Event.id == Signup.event_id)
        .where(Signup.runner_id == user.id, Event.date >= today)
        .options(selectinload(Signup.group), selectinload(Signup.event))
        .order_by(Event.date)
    )
    return [
        MySignupEntry(
            signup_id=s.id,
            group_id=s.group_id,
            group_name=s.group.name,
            location=s.group.location,
            event_id=s.event_id,
            event_title=s.event.title,
            event_date=s.event.date,
            start_time=s.group.start_time,
        )
        for s in rows
    ]


@router.get("/groups/{group_id}/signups", response_model=SignupRoster)
async def group_signup_roster(group_id: int, session: SessionDep) -> SignupRoster:
    """Who's signed up (intent, not the post-event protocol) — the frontend
    only shows this for groups whose event hasn't happened yet."""
    group = await session.get(Group, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
    rows = await session.scalars(
        select(Signup)
        .where(Signup.group_id == group_id)
        .options(selectinload(Signup.runner))
        .order_by(Signup.created_at)
    )
    entries = [
        SignupRosterEntry(
            signup_id=s.id,
            runner_id=s.runner_id,
            display_name=f"{s.runner.first_name} {s.runner.last_name}",
            avatar=s.runner.avatar,
        )
        for s in rows
    ]
    return SignupRoster(group_id=group_id, count=len(entries), entries=entries)


@router.post(
    "/groups/{group_id}/signups", response_model=SignupOut, status_code=status.HTTP_201_CREATED
)
async def create_signup(group_id: int, user: CurrentUser, session: SessionDep) -> Signup:
    group = await session.get(Group, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")

    # One signup per event: if the runner already has one for this event
    # (possibly a different group), move it here instead of erroring —
    # picking a different pace group shouldn't require unsigning first.
    existing = await session.scalar(
        select(Signup).where(Signup.event_id == group.event_id, Signup.runner_id == user.id)
    )
    if existing is not None:
        if existing.group_id != group_id:
            existing.group_id = group_id
            await session.commit()
            await session.refresh(existing)
        return existing

    signup = Signup(group_id=group_id, runner_id=user.id, event_id=group.event_id)
    session.add(signup)
    await session.commit()
    await session.refresh(signup)
    return signup


@router.delete("/signups/{signup_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_signup(signup_id: int, user: CurrentUser, session: SessionDep) -> None:
    signup = await session.get(Signup, signup_id)
    if signup is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Signup not found")
    if signup.runner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your signup")
    await session.delete(signup)
    await session.commit()
