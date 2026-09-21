from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, OptionalUser, SessionDep
from app.core.timezone import today_msk
from app.models.attendance import AttendanceRecord
from app.models.event import Event
from app.models.group import Group
from app.models.result import Result
from app.models.signup import Signup
from app.schemas.signup import (
    AwaitingResultEntry,
    EventSignupState,
    GroupSignupState,
    MySignupEntry,
    SignupGroupSummary,
    SignupOut,
    SignupRoster,
    SignupRosterEntry,
)
from app.services.avatar_service import visible_avatar
from app.services.event_time import group_has_started
from app.services.participation_service import get_group_participation

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
    return EventSignupState(signed_up=True, group_id=signup.group_id, group_name=signup.group.name)


@router.get("/users/me/signups", response_model=list[MySignupEntry])
async def my_signups(user: CurrentUser, session: SessionDep) -> list[MySignupEntry]:
    """Upcoming events the runner has signed up for. A same-day event moves to
    "Загрузить результат" (see my_awaiting_results) the moment its group
    actually starts, rather than lingering here until midnight — otherwise a
    today's-event signup shows in both lists at once for the rest of the day."""
    today = today_msk()
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
        if not group_has_started(s.group.start_time, s.event.date)
    ]


@router.get("/users/me/signups/awaiting-result", response_model=list[AwaitingResultEntry])
async def my_awaiting_results(
    user: CurrentUser,
    session: SessionDep,
    include_group_id: int | None = Query(default=None),
) -> list[AwaitingResultEntry]:
    """Past events the runner signed up to where they can self-report a result
    (or it's pending) — the entry point for uploading before the CSV protocol
    exists. Fully-approved ones drop off (they're already in the protocol).
    Otherwise this lingers forever for a signup that never turned into an
    actual run — the frontend offers signup_id so the runner can dismiss it
    themselves ("я не бегал(а)", DELETE /signups/{id}, same endpoint as
    unsigning before the event).

    `include_group_id` is the "Я бегал(а)" deep link from a group page: that
    group is added to the list even without a signup (signup_id null — nothing
    to dismiss), so a runner who forgot to sign up still enters their result in
    this same place. Skipped when the group hasn't started, the runner already
    has a record in another group of the event, or the result is approved."""
    today = today_msk()
    signups = list(
        await session.scalars(
            select(Signup)
            .join(Event, Event.id == Signup.event_id)
            .where(Signup.runner_id == user.id, Event.date <= today)
            .options(selectinload(Signup.group), selectinload(Signup.event))
            .order_by(Event.date.desc())
        )
    )

    out: list[AwaitingResultEntry] = []
    for s in signups:
        # Go by where the runner actually is in this event, not where they
        # signed up: a record in another group (they signed up for D-21 but the
        # protocol / their own report has them in X-34) supersedes the signup.
        record = await session.scalar(
            select(AttendanceRecord)
            .join(Group, Group.id == AttendanceRecord.group_id)
            .where(Group.event_id == s.event_id, AttendanceRecord.runner_id == user.id)
            .options(selectinload(AttendanceRecord.result), selectinload(AttendanceRecord.group))
            .order_by(AttendanceRecord.id)
            .limit(1)
        )
        group = record.group if record is not None else s.group
        if record is None and not group_has_started(group.start_time, s.event.date):
            continue
        result: Result | None = record.result if record is not None else None
        if result is not None and result.status.value == "approved":
            continue  # done — in the protocol already
        out.append(
            AwaitingResultEntry(
                signup_id=s.id,
                group_id=group.id,
                group_name=group.name,
                location=group.location,
                event_id=s.event_id,
                event_title=s.event.title,
                event_date=s.event.date,
                start_time=group.start_time,
                has_record=record is not None,
                has_result=result is not None,
                moderation_status=result.status.value if result is not None else None,
            )
        )

    if include_group_id is not None and all(e.group_id != include_group_id for e in out):
        group = await session.get(Group, include_group_id)
        event = await session.get(Event, group.event_id) if group is not None else None
        if group is not None and event is not None:
            if group_has_started(group.start_time, event.date):
                part = await get_group_participation(session, user.id, group)
                approved = part.result is not None and part.result.status.value == "approved"
                if part.other_group is None and not approved:
                    out.insert(
                        0,
                        AwaitingResultEntry(
                            signup_id=None,
                            group_id=group.id,
                            group_name=group.name,
                            location=group.location,
                            event_id=event.id,
                            event_title=event.title,
                            event_date=event.date,
                            start_time=group.start_time,
                            has_record=part.record is not None,
                            has_result=part.result is not None,
                            moderation_status=(
                                part.result.status.value if part.result is not None else None
                            ),
                        ),
                    )
    return out


@router.get("/groups/{group_id}/signups", response_model=SignupRoster)
async def group_signup_roster(
    group_id: int, session: SessionDep, viewer: OptionalUser
) -> SignupRoster:
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
            avatar=visible_avatar(s.runner, viewer.id if viewer else None),
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

    # No signing up after the fact: a signup is an intent to run, which only
    # makes sense before the run starts. Once the group has started, the way in
    # is a self-reported result or a CSV import (actual participation), not a
    # retroactive signup.
    event = await session.get(Event, group.event_id)
    assert event is not None
    if group_has_started(group.start_time, event.date):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Тренировка уже началась — запись закрыта.",
        )

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
