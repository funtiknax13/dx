"""Counts of things waiting on a staff member — guest-merge claims and results
pending moderation. Both are Admin-only actions (see CLAUDE.md), unlike
support tickets which Organizer also handles — see app.api.staff."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AvatarReview, ClaimStatus, ModerationStatus
from app.models.guest_claim import GuestClaim
from app.models.profile_edit_request import ProfileEditRequest
from app.models.result import Result
from app.models.user import User


async def pending_claims_count(session: AsyncSession) -> int:
    result = await session.scalar(
        select(func.count(GuestClaim.id)).where(GuestClaim.status == ClaimStatus.pending)
    )
    return result or 0


async def pending_moderation_count(session: AsyncSession) -> int:
    result = await session.scalar(
        select(func.count(Result.id)).where(Result.status == ModerationStatus.pending)
    )
    return result or 0


async def pending_avatar_count(session: AsyncSession) -> int:
    result = await session.scalar(
        select(func.count(User.id)).where(
            User.avatar_review == AvatarReview.pending,
            User.avatar.is_not(None),
        )
    )
    return result or 0


async def pending_profile_review_count(session: AsyncSession) -> int:
    result = await session.scalar(
        select(func.count(ProfileEditRequest.id)).where(
            ProfileEditRequest.status == ModerationStatus.pending
        )
    )
    return result or 0
