from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.models.enums import UserRole
from app.services.staff_attention_service import pending_claims_count, pending_moderation_count
from app.services.support_service import unread_ticket_count_for_staff

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("/attention-counts")
async def attention_counts(user: CurrentUser, session: SessionDep) -> dict[str, int]:
    """Powers the "needs a look" badge on the main site's Admin Tools button —
    so staff notice without having to open admin-tools first. Tickets are
    shared between Organizer and Admin; claims/moderation are Admin-only
    (see CLAUDE.md), so an organizer always gets 0 for those."""
    if user.role not in (UserRole.admin, UserRole.organizer):
        return {"tickets": 0, "claims": 0, "moderation": 0}
    tickets = await unread_ticket_count_for_staff(session)
    if user.role != UserRole.admin:
        return {"tickets": tickets, "claims": 0, "moderation": 0}
    return {
        "tickets": tickets,
        "claims": await pending_claims_count(session),
        "moderation": await pending_moderation_count(session),
    }
