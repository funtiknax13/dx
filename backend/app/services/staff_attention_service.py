"""Counts of things waiting on a staff member — guest-merge claims and results
pending moderation. Both are Admin-only actions (see CLAUDE.md), unlike
support tickets which Organizer also handles — see app.api.staff."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ClaimStatus, ModerationStatus
from app.models.guest_claim import GuestClaim
from app.models.result import Result


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
