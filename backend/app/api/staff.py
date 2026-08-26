from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.models.enums import StaffPermission, UserRole
from app.services.permissions_service import permissions_for
from app.services.staff_attention_service import pending_claims_count, pending_moderation_count
from app.services.support_service import unread_ticket_count_for_staff

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("/attention-counts")
async def attention_counts(user: CurrentUser, session: SessionDep) -> dict[str, int]:
    """Powers the "needs a look" badge on the main site's Admin Tools button —
    so staff notice without having to open admin-tools first. Tickets are
    shared between Organizer and Admin; claims/moderation are Admin-only by
    default, delegable per-organizer (see StaffPermission) — an organizer
    without the matching grant gets 0 for that key."""
    if user.role not in (UserRole.admin, UserRole.organizer):
        return {"tickets": 0, "claims": 0, "moderation": 0}
    tickets = await unread_ticket_count_for_staff(session)
    perms = await permissions_for(session, user)
    claims = await pending_claims_count(session) if StaffPermission.guest_claims in perms else 0
    moderation = (
        await pending_moderation_count(session) if StaffPermission.results_review in perms else 0
    )
    return {"tickets": tickets, "claims": claims, "moderation": moderation}
