from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.admin.tools_common import login_redirect, require_permission, templates
from app.core.db import SessionLocal
from app.models.enums import StaffPermission
from app.models.user import User
from app.services.rating_service import milestone_candidates

router = APIRouter(prefix="/admin-tools", tags=["admin-milestones"], include_in_schema=False)


async def _require_milestones(request: Request) -> User | None:
    return await require_permission(request, StaffPermission.milestones)


@router.get("/milestones", response_class=HTMLResponse, response_model=None)
async def milestones_page(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_milestones(request)
    if user is None:
        return login_redirect()

    async with SessionLocal() as session:
        entries = await milestone_candidates(session)

    # Bucketed by how many finishes are left, same shape as the birthdays
    # page's "today" / "upcoming" split — remaining=0 is the DX where the
    # milestone itself happens.
    at_milestone = [e for e in entries if e.remaining == 0]
    one_left = [e for e in entries if e.remaining == 1]
    two_left = [e for e in entries if e.remaining == 2]

    return templates.TemplateResponse(
        request,
        "milestones.html",
        {
            "active": "milestones",
            "tools_user": user,
            "at_milestone": at_milestone,
            "one_left": one_left,
            "two_left": two_left,
            "total": len(entries),
        },
    )
