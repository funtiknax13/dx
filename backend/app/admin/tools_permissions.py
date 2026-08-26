from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.admin.tools_common import get_tools_user, login_redirect, templates
from app.core.db import SessionLocal
from app.models.enums import StaffPermission, UserRole
from app.models.user import User
from app.services.permissions_service import PERMISSION_META, permissions_for, set_permissions

router = APIRouter(prefix="/admin-tools", tags=["admin-permissions"], include_in_schema=False)

_VALID_PERMISSIONS = {p.value for p in StaffPermission}


async def _require_admin(request: Request) -> User | None:
    """Granting admin-tools access is itself never delegable — an organizer,
    even one with every other permission granted, can't hand out access (to
    themselves or anyone else). Always a hard admin check, unlike every other
    page in this module."""
    user = await get_tools_user(request)
    if user is None or user.role != UserRole.admin:
        return None
    return user


@router.get("/permissions", response_class=HTMLResponse, response_model=None)
async def permissions_page(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        organizers = list(
            await session.scalars(
                select(User).where(User.role == UserRole.organizer).order_by(User.first_name)
            )
        )
        rows = [{"organizer": o, "granted": await permissions_for(session, o)} for o in organizers]
    return templates.TemplateResponse(
        request,
        "permissions.html",
        {
            "active": "permissions",
            "tools_user": user,
            "rows": rows,
            "catalog": PERMISSION_META,
            "flash": request.query_params.get("flash"),
            "flash_error": request.query_params.get("flash_error"),
        },
    )


@router.post("/permissions/{user_id}", response_model=None)
async def permissions_save(
    request: Request,
    user_id: int,
    permissions: list[str] = Form([]),  # noqa: B006
) -> RedirectResponse:
    admin = await _require_admin(request)
    if admin is None:
        return login_redirect()
    async with SessionLocal() as session:
        target = await session.get(User, user_id)
        if target is None or target.role != UserRole.organizer:
            return RedirectResponse(
                "/admin-tools/permissions?flash_error=Пользователь не найден или не организатор",
                status_code=303,
            )
        granted = {StaffPermission(p) for p in permissions if p in _VALID_PERMISSIONS}
        await set_permissions(session, target, granted, granted_by=admin)
        await session.commit()
        name = f"{target.first_name} {target.last_name}"
    return RedirectResponse(
        f"/admin-tools/permissions?flash=Права для {name} обновлены", status_code=303
    )
