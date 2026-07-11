from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.models.group import Group
from app.models.signup import Signup
from app.schemas.signup import GroupSignupState, SignupOut, SignupRoster, SignupRosterEntry

router = APIRouter(tags=["signups"])


@router.get("/groups/{group_id}/signups/me", response_model=GroupSignupState)
async def my_signup_state(
    group_id: int, user: CurrentUser, session: SessionDep
) -> GroupSignupState:
    signup = await session.scalar(
        select(Signup).where(Signup.group_id == group_id, Signup.runner_id == user.id)
    )
    return GroupSignupState(signed_up=signup is not None, signup_id=signup.id if signup else None)


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

    existing = await session.scalar(
        select(Signup).where(Signup.group_id == group_id, Signup.runner_id == user.id)
    )
    if existing is not None:
        return existing

    signup = Signup(group_id=group_id, runner_id=user.id)
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
