"""Guest accounts: placeholder Users auto-created from a CSV row that doesn't match
any registered account by email, so the run shows up in the protocol/rating right
away instead of sitting invisible in a moderation queue.

A guest can later be claimed by a real, registered user ("this is me") and, once an
Admin approves the claim, merged into that account — see merge_guest_into below.
"""

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.attendance import AttendanceRecord
from app.models.enums import ClaimStatus, UserRole
from app.models.guest_claim import GuestClaim
from app.models.signup import Signup
from app.models.user import User


def split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return (parts[0] if parts else full_name.strip()) or "Guest", ""


async def find_real_user_by_email(session: AsyncSession, email: str | None) -> User | None:
    if not email or not email.strip():
        return None
    result = await session.scalar(
        select(User).where(
            func.lower(User.email) == email.strip().lower(), User.is_guest.is_(False)
        )
    )
    return result


async def find_guest_by_name(session: AsyncSession, raw_name: str) -> User | None:
    """Find any guest account (merged or not) with a matching first+last name —
    used to avoid creating a duplicate guest for the same person across separate
    CSV imports, and to auto-redirect to the real account once a same-named guest
    has already been merged."""
    first_name, last_name = split_name(raw_name)
    result = await session.scalar(
        select(User).where(
            User.is_guest.is_(True),
            func.lower(User.first_name) == first_name.strip().lower(),
            func.lower(User.last_name) == last_name.strip().lower(),
        )
    )
    return result


async def resolve_runner_for_csv_row(
    session: AsyncSession, raw_name: str, raw_email: str | None
) -> tuple[User, str]:
    """Resolve which account a CSV row belongs to, in priority order:

    1. `raw_email` exactly matches a registered (non-guest) account -> that account.
    2. `raw_name` matches an already-*merged* guest -> the real account it merged
       into (so once one CSV row for a person is claimed, later imports of the same
       name resolve straight to the real account, no repeat claims needed).
    3. `raw_name` matches an existing *unmerged* guest -> reuse it, rather than
       spinning up a second guest for the same person.
    4. No match at all -> create a fresh guest account.

    Returns (user, resolution) where resolution is one of "email_match",
    "merge_redirect", "guest_reused", "guest_created" — used for the import summary.
    """
    matched = await find_real_user_by_email(session, raw_email)
    if matched is not None:
        return matched, "email_match"

    existing_guest = await find_guest_by_name(session, raw_name)
    if existing_guest is not None:
        if existing_guest.merged_into_id is not None:
            real_user = await session.get(User, existing_guest.merged_into_id)
            if real_user is not None:
                return real_user, "merge_redirect"
        else:
            return existing_guest, "guest_reused"

    guest = await create_guest(session, raw_name)
    return guest, "guest_created"


async def create_guest(session: AsyncSession, raw_name: str) -> User:
    first_name, last_name = split_name(raw_name)
    guest = User(
        first_name=first_name,
        last_name=last_name,
        # Synthetic, unique, unreachable — guests never log in with these.
        email=f"guest-{uuid.uuid4().hex}@dh.guest",
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role=UserRole.runner,
        email_verified=False,
        is_guest=True,
    )
    session.add(guest)
    await session.flush()
    return guest


async def merge_guest_into(session: AsyncSession, guest: User, real_user: User) -> None:
    """Reassign a guest's history onto a real account and mark the guest merged.

    The guest row is kept (not deleted) for audit, per product decision — its
    AttendanceRecords/Signups move to `real_user`, so the guest's own protocol/
    rating/profile naturally go empty rather than needing special-casing elsewhere.
    """
    if guest.id == real_user.id or not guest.is_guest:
        raise ValueError("Not a mergeable guest account")

    guest_records = list(
        await session.scalars(
            select(AttendanceRecord).where(AttendanceRecord.runner_id == guest.id)
        )
    )
    for record in guest_records:
        record.runner_id = real_user.id

    # A guest never signs itself up, but handle it defensively: move signups,
    # dropping any that would collide with one the real user already has.
    existing_group_ids = {
        gid
        for gid in await session.scalars(
            select(Signup.group_id).where(Signup.runner_id == real_user.id)
        )
    }
    guest_signups = list(
        await session.scalars(select(Signup).where(Signup.runner_id == guest.id))
    )
    for signup in guest_signups:
        if signup.group_id in existing_group_ids:
            await session.delete(signup)
        else:
            signup.runner_id = real_user.id
            existing_group_ids.add(signup.group_id)

    guest.merged_into_id = real_user.id

    # Any other pending claims on this now-merged guest no longer make sense.
    other_claims = list(
        await session.scalars(
            select(GuestClaim).where(
                GuestClaim.guest_user_id == guest.id,
                GuestClaim.status == ClaimStatus.pending,
            )
        )
    )
    for claim in other_claims:
        claim.status = ClaimStatus.rejected
        claim.decided_at = datetime.now(UTC)

    await session.flush()
