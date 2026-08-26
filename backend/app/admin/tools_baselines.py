from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app.admin.tools_common import login_redirect, require_permission, templates
from app.core.db import SessionLocal
from app.models.enums import StaffPermission
from app.models.user import User
from app.services.baseline_import_service import import_baseline_csv

router = APIRouter(prefix="/admin-tools", tags=["admin-baselines"], include_in_schema=False)


async def _require_access(request: Request) -> User | None:
    return await require_permission(request, StaffPermission.baselines)


@router.get("/import-baselines", response_class=HTMLResponse, response_model=None)
async def import_baselines_page(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_access(request)
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
    user = await _require_access(request)
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
