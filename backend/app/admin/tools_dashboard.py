import jwt
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.admin.tools_common import (
    SESSION_KEY,
    get_tools_user,
    login_redirect,
    templates,
    verify_tools_credentials,
)
from app.core.db import SessionLocal
from app.core.security import ACCESS, decode_token
from app.models.enums import UserRole
from app.models.user import User

router = APIRouter(prefix="/admin-tools", tags=["admin-tools"], include_in_schema=False)


@router.get("/sso", response_model=None)
async def sso(request: Request, token: str) -> RedirectResponse:
    """Single-sign-on bridge from the frontend SPA: exchanges a short-lived JWT
    access token (already proven valid by the frontend login) for the same
    session-cookie the admin-tools pages (and, for admins, SQLAdmin) read — no
    second login. Reached via a link the frontend only shows to organizer/admin."""
    try:
        user_id = int(decode_token(token, ACCESS))
    except (jwt.PyJWTError, ValueError):
        return RedirectResponse("/admin-tools/login?error=expired", status_code=302)

    async with SessionLocal() as session:
        user = await session.get(User, user_id)
    if user is None or user.role not in (UserRole.organizer, UserRole.admin):
        return RedirectResponse("/admin-tools/login?error=forbidden", status_code=302)

    request.session[SESSION_KEY] = str(user.id)
    return RedirectResponse("/admin-tools", status_code=302)


@router.get("/login", response_class=HTMLResponse, response_model=None)
async def login_page(request: Request) -> HTMLResponse:
    error = request.query_params.get("error")
    message = {
        "expired": "Ссылка устарела, войдите заново на сайте.",
        "forbidden": "Доступ к admin-tools есть только у организаторов и админов.",
        "invalid": "Неверный email или пароль.",
    }.get(error or "")
    return templates.TemplateResponse(
        request, "login.html", {"flash_error": message, "no_nav": True}
    )


@router.post("/login", response_model=None)
async def login_submit(
    request: Request, email: str = Form(...), password: str = Form(...)
) -> RedirectResponse | HTMLResponse:
    user = await verify_tools_credentials(email, password)
    if user is None:
        return RedirectResponse("/admin-tools/login?error=invalid", status_code=302)
    request.session[SESSION_KEY] = str(user.id)
    return RedirectResponse("/admin-tools", status_code=302)


@router.post("/logout", response_model=None)
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/admin-tools/login", status_code=302)


@router.get("", response_class=HTMLResponse, response_model=None)
async def dashboard(request: Request) -> HTMLResponse | RedirectResponse:
    user = await get_tools_user(request)
    if user is None:
        return login_redirect()
    return templates.TemplateResponse(
        request, "dashboard.html", {"active": "dashboard", "tools_user": user}
    )
