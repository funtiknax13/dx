from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.admin.tools_common import get_tools_user, login_redirect, templates
from app.core.db import SessionLocal
from app.models.enums import ModerationStatus, UserRole
from app.models.profile_edit_request import ProfileEditRequest
from app.models.user import User
from app.services.profile_review_service import approve, is_awaiting_first_review, reject

router = APIRouter(prefix="/admin-tools", tags=["admin-profile-review"], include_in_schema=False)

# Field names shown in the queue, in a stable, readable order — matches
# profile_review_service.MODERATED_FIELDS but skips city_id (city carries the
# same information for a human reviewer).
FIELD_LABELS = {
    "first_name": "Имя",
    "last_name": "Фамилия",
    "city": "Город",
    "gender": "Пол",
    "birthday": "Дата рождения",
    "phone": "Телефон",
    "running_club": "Беговой клуб",
    "parent_first_name": "Имя опекуна",
    "parent_last_name": "Фамилия опекуна",
    "parent_phone": "Телефон опекуна",
}


async def _require_admin(request: Request) -> User | None:
    user = await get_tools_user(request)
    if user is None or user.role != UserRole.admin:
        return None
    return user


@router.get("/profile-review", response_class=HTMLResponse, response_model=None)
async def profile_review_queue(request: Request) -> HTMLResponse | RedirectResponse:
    """Post-moderation queue for the whole profile form (name, birthday, city,
    gender, phone, running club, guardian contacts) — see ProfileEditRequest.
    Admin-only, same restriction as CSV import/claims/avatars."""
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        requests = list(
            await session.scalars(
                select(ProfileEditRequest)
                .where(ProfileEditRequest.status == ModerationStatus.pending)
                .options(selectinload(ProfileEditRequest.user))
                .order_by(ProfileEditRequest.id)
            )
        )
    rows = [
        {
            "req": r,
            "is_first_review": is_awaiting_first_review(r.user),
            "changes": [
                (FIELD_LABELS.get(f, f), v) for f, v in r.changes.items() if f != "city_id"
            ],
        }
        for r in requests
    ]
    return templates.TemplateResponse(
        request,
        "profile_review.html",
        {
            "active": "profile-review",
            "tools_user": user,
            "rows": rows,
            "flash": request.query_params.get("flash"),
        },
    )


@router.post("/profile-review/{request_id}/approve", response_model=None)
async def approve_profile_edit(request: Request, request_id: int) -> RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        edit_request = await session.get(
            ProfileEditRequest, request_id, options=[selectinload(ProfileEditRequest.user)]
        )
        if edit_request is not None and edit_request.status == ModerationStatus.pending:
            await approve(session, edit_request)
            await session.commit()
    return RedirectResponse("/admin-tools/profile-review?flash=Изменения приняты", status_code=303)


@router.post("/profile-review/{request_id}/reject", response_model=None)
async def reject_profile_edit(
    request: Request, request_id: int, reason: str = Form("")
) -> RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        edit_request = await session.get(
            ProfileEditRequest, request_id, options=[selectinload(ProfileEditRequest.user)]
        )
        if edit_request is not None and edit_request.status == ModerationStatus.pending:
            await reject(session, edit_request, user, reason)
            await session.commit()
    return RedirectResponse(
        "/admin-tools/profile-review?flash=Изменения отклонены, пользователь уведомлён",
        status_code=303,
    )
