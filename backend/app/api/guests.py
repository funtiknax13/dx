from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.models.enums import ClaimStatus
from app.models.guest_claim import GuestClaim
from app.models.user import User
from app.schemas.guest import ClaimOut, GuestOut, MyClaimOut
from app.services.name_search import flexible_name_filter

router = APIRouter(prefix="/guests", tags=["guests"])


@router.get("", response_model=list[GuestOut])
async def search_guests(q: str, session: SessionDep) -> list[User]:
    """Search unmerged guest profiles by name, so a real user can find "themselves"
    among CSV-imported guest accounts and claim one."""
    q = q.strip()
    if len(q) < 2:
        return []
    guests = await session.scalars(
        select(User)
        .where(
            User.is_guest.is_(True),
            User.merged_into_id.is_(None),
            flexible_name_filter(q, include_email=False),
        )
        .order_by(User.id)
        .limit(20)
    )
    return list(guests)


@router.post("/{guest_id}/claim", response_model=ClaimOut, status_code=status.HTTP_201_CREATED)
async def claim_guest(guest_id: int, user: CurrentUser, session: SessionDep) -> GuestClaim:
    guest = await session.get(User, guest_id)
    if guest is None or not guest.is_guest:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guest profile not found")
    if guest.merged_into_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Guest profile is already merged")

    existing = await session.scalar(
        select(GuestClaim).where(
            GuestClaim.guest_user_id == guest_id,
            GuestClaim.claimant_user_id == user.id,
            GuestClaim.status == ClaimStatus.pending,
        )
    )
    if existing is not None:
        return existing

    claim = GuestClaim(guest_user_id=guest_id, claimant_user_id=user.id)
    session.add(claim)
    await session.commit()
    await session.refresh(claim)
    return claim


@router.get("/me/claims", response_model=list[MyClaimOut])
async def my_claims(user: CurrentUser, session: SessionDep) -> list[GuestClaim]:
    claims = await session.scalars(
        select(GuestClaim)
        .where(GuestClaim.claimant_user_id == user.id)
        .options(selectinload(GuestClaim.guest))
        .order_by(GuestClaim.id.desc())
    )
    return list(claims)
