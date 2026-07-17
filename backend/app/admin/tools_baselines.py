from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app.admin.tools_common import get_tools_user, login_redirect, templates
from app.core.db import SessionLocal
from app.models.enums import UserRole
from app.models.user import User
from app.services.baseline_import_service import import_baseline_csv

router = APIRouter(prefix="/admin-tools", tags=["admin-baselines"], include_in_schema=False)


async def _require_admin(request: Request) -> User | None:
    """Same restriction as CSV attendance import — Admin-only per CLAUDE.md,
    even though the rest of admin-tools is also open to organizers."""
    user = await get_tools_user(request)
    if user is None or user.role != UserRole.admin:
        return None
    return user


@router.get("/import-baselines", response_class=HTMLResponse, response_model=None)
async def import_baselines_page(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    return templates.TemplateResponse(
        request,
        "import_baselines.html",
        {"active": "import-baselines", "tools_user": user, "result": None},
    )


@router.post("/import-baselines", response_class=HTMLResponse, response_model=None)
async def import_baselines_submit(
    request: Request, file: UploadFile | None = None
) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()

    flash_error = None
    result = None
    async with SessionLocal() as session:
        if file is None or not file.filename:
            flash_error = "Выберите CSV-файл"
        else:
            content = await file.read()
            try:
                result = await import_baseline_csv(session, content)
                await session.commit()
            except ValueError as exc:
                flash_error = str(exc)

    return templates.TemplateResponse(
        request,
        "import_baselines.html",
        {
            "active": "import-baselines",
            "tools_user": user,
            "result": result,
            "flash_error": flash_error,
        },
    )
