from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.admin.tools_common import get_tools_user, login_redirect, templates
from app.core.db import SessionLocal
from app.models.enums import AvatarReview, StaffPermission
from app.models.user import User
from app.services.media_service import delete_media
from app.services.support_service import create_staff_ticket

router = APIRouter(prefix="/admin-tools", tags=["admin-avatars"], include_in_schema=False)


@router.get("/avatars", response_class=HTMLResponse, response_model=None)
async def avatars_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Post-moderation queue: avatars that applied immediately and now await a
    moderator's look (see AvatarReview). Admin by default, delegable to an
    organizer via StaffPermission.avatars."""
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    if StaffPermission.avatars not in user.granted_permissions:
        return RedirectResponse("/admin-tools", status_code=303)
    async with SessionLocal() as session:
        users = list(
            await session.scalars(
                select(User)
                .where(User.avatar_review == AvatarReview.pending, User.avatar.is_not(None))
                .order_by(User.id.desc())
            )
        )
    return templates.TemplateResponse(
        request,
        "avatars.html",
        {
            "active": "avatars",
            "tools_user": user,
            "users": users,
            "flash": request.query_params.get("flash"),
        },
    )


@router.post("/avatars/{user_id}/approve", response_model=None)
async def approve_avatar(request: Request, user_id: int) -> RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    if StaffPermission.avatars not in user.granted_permissions:
        return RedirectResponse("/admin-tools", status_code=303)
    async with SessionLocal() as session:
        target = await session.get(User, user_id)
        if target is not None:
            target.avatar_review = AvatarReview.approved
            await session.commit()
    return RedirectResponse("/admin-tools/avatars?flash=Аватар оставлен", status_code=303)


def _removal_message(reason: str) -> str:
    lines = ["Ваше фото профиля снято модератором."]
    reason = reason.strip()
    if reason:
        lines += ["", f"Причина: {reason}"]
    lines += ["", "При желании загрузите другое фото."]
    return "\n".join(lines)


@router.post("/avatars/{user_id}/remove", response_model=None)
async def remove_avatar(request: Request, user_id: int, reason: str = Form("")) -> RedirectResponse:
    """Remove an unsuitable photo: clears it (runner reverts to initials) and
    tells them why (the moderator's reason) via a closed support ticket, same
    channel as a rejected result. The record leaves the queue either way."""
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    if StaffPermission.avatars not in user.granted_permissions:
        return RedirectResponse("/admin-tools", status_code=303)
    async with SessionLocal() as session:
        target = await session.get(User, user_id)
        if target is not None and target.avatar:
            delete_media(target.avatar)
            target.avatar = None
            target.avatar_review = AvatarReview.approved
            if not target.is_guest:
                await create_staff_ticket(
                    session,
                    recipient=target,
                    admin=user,
                    body=_removal_message(reason),
                )
            await session.commit()
    return RedirectResponse(
        "/admin-tools/avatars?flash=Аватар удалён, пользователь уведомлён", status_code=303
    )
