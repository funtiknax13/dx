from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, select

from app.admin.tools_common import get_tools_user, login_redirect, templates
from app.core.db import SessionLocal
from app.models.enums import StaffPermission, UserRole
from app.models.organizer_permission import OrganizerPermission
from app.models.user import User
from app.services.name_search import flexible_name_filter
from app.services.permissions_service import PERMISSION_META, permissions_for, set_permissions

router = APIRouter(prefix="/admin-tools", tags=["admin-permissions"], include_in_schema=False)

_VALID_PERMISSIONS = {p.value for p in StaffPermission}


async def _require_admin(request: Request) -> User | None:
    """Granting admin-tools access — and assigning/removing the organizer
    role itself — is never delegable — an organizer, even one with every
    other permission granted, can't hand out access or promote anyone.
    Always a hard admin check, unlike every other page in this module."""
    user = await get_tools_user(request)
    if user is None or user.role != UserRole.admin:
        return None
    return user


@router.get("/permissions", response_class=HTMLResponse, response_model=None)
async def permissions_page(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    q = request.query_params.get("q", "").strip()
    async with SessionLocal() as session:
        organizers = list(
            await session.scalars(
                select(User).where(User.role == UserRole.organizer).order_by(User.first_name)
            )
        )
        rows = [{"organizer": o, "granted": await permissions_for(session, o)} for o in organizers]
        search_results: list[User] = []
        if q:
            search_results = list(
                await session.scalars(
                    select(User)
                    .where(
                        User.role == UserRole.runner,
                        User.is_guest.is_(False),
                        flexible_name_filter(q),
                    )
                    .order_by(User.id)
                    .limit(10)
                )
            )
    return templates.TemplateResponse(
        request,
        "permissions.html",
        {
            "active": "permissions",
            "tools_user": user,
            "rows": rows,
            "catalog": PERMISSION_META,
            "q": q,
            "search_results": search_results,
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


@router.post("/permissions/{user_id}/promote", response_model=None)
async def promote_to_organizer(request: Request, user_id: int) -> RedirectResponse:
    """Makes a runner an organizer — no permissions granted automatically
    (secure default, same as everywhere else in this system); admin checks
    boxes afterward via the row that now appears in the table below."""
    admin = await _require_admin(request)
    if admin is None:
        return login_redirect()
    async with SessionLocal() as session:
        target = await session.get(User, user_id)
        if target is None or target.role != UserRole.runner or target.is_guest:
            flash_error = "Нельзя назначить этого пользователя организатором"
            return RedirectResponse(
                f"/admin-tools/permissions?flash_error={flash_error}", status_code=303
            )
        target.role = UserRole.organizer
        await session.commit()
        name = f"{target.first_name} {target.last_name}"
    return RedirectResponse(
        f"/admin-tools/permissions?flash={name} назначен(а) организатором", status_code=303
    )


@router.post("/permissions/{user_id}/demote", response_model=None)
async def demote_organizer(request: Request, user_id: int) -> RedirectResponse:
    """Removes the organizer role and every OrganizerPermission row for this
    user in one step — a grant is meaningless for a non-organizer
    (set_permissions already enforces role == organizer), so this actively
    cleans up rather than leaving dead rows a later re-promotion would
    silently inherit without admin reviewing them. Past events they created
    stay intact and admin-editable (Event.created_by is unaffected, and
    can_manage_event's role == admin clause covers admin regardless of the
    creator's current role)."""
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
        await session.execute(
            delete(OrganizerPermission).where(OrganizerPermission.user_id == target.id)
        )
        target.role = UserRole.runner
        await session.commit()
        name = f"{target.first_name} {target.last_name}"
    return RedirectResponse(
        f"/admin-tools/permissions?flash=Роль организатора снята у {name}", status_code=303
    )
