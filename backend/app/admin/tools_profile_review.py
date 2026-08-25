from datetime import date
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.admin.tools_common import get_tools_user, login_redirect, templates
from app.core.db import SessionLocal
from app.models.city import City
from app.models.enums import ModerationStatus, UserRole
from app.models.profile_edit_request import ProfileEditRequest
from app.models.user import User
from app.services.profile_review_service import (
    MODERATED_FIELDS,
    approve,
    is_awaiting_first_review,
    reject,
)

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

DISPLAY_FIELDS = [f for f in MODERATED_FIELDS if f != "city_id"]

_GENDER_LABELS = {"male": "Мужской", "female": "Женский"}


def _format_value(field: str, value: Any) -> str:
    if value is None or value == "":
        return "—"
    if field == "gender":
        return _GENDER_LABELS.get(value, str(value))
    if field == "birthday":
        d = value if isinstance(value, date) else date.fromisoformat(value)
        return d.strftime("%d.%m.%Y")
    return str(value)


async def _proposed_city_display(session: AsyncSession, changes: dict[str, Any]) -> str | None:
    """The "city" entry to show, even when a caller only staged city_id
    without the matching city text (the profile form always sends both —
    see ProfilePage.tsx — but nothing stops some other API client from
    submitting city_id alone, and this queue must not go blind to a city
    change just because of that)."""
    if "city" in changes:
        return _format_value("city", changes["city"])
    if "city_id" not in changes:
        return None
    city_id = changes["city_id"]
    if city_id is None:
        return _format_value("city", None)
    city = await session.get(City, city_id)
    return city.name if city is not None else f"#{city_id}"


async def _row_fields(
    session: AsyncSession, request: ProfileEditRequest, is_first_review: bool
) -> list[dict[str, Any]]:
    """One entry per field shown in the queue row. A first-ever registration
    has no real "before" to compare against (the account didn't exist), so it
    only lists what's proposed; a later edit shows the *whole* profile for
    context, with only the fields actually being changed marked (было →
    стало) — everything else displayed plainly as-is."""
    city_display = await _proposed_city_display(session, request.changes)
    if is_first_review:
        fields = [
            {
                "label": FIELD_LABELS.get(f, f),
                "changed": True,
                "current": None,
                "proposed": _format_value(f, v),
            }
            for f, v in request.changes.items()
            if f not in ("city_id", "city")
        ]
        if city_display is not None:
            fields.append(
                {"label": "Город", "changed": True, "current": None, "proposed": city_display}
            )
        return fields
    fields = []
    for f in DISPLAY_FIELDS:
        current = _format_value(f, getattr(request.user, f))
        proposed = (
            city_display
            if f == "city"
            else (_format_value(f, request.changes[f]) if f in request.changes else None)
        )
        # A backfilled request's "changes" is a snapshot of the account as it
        # stood at migration time (see the introducing migration) rather
        # than a genuine diff — было/стало collapses to the same value there,
        # which would otherwise show every field as "changed" to itself.
        # Only a real difference counts as changed.
        changed = proposed is not None and proposed != current
        if not changed and current == "—":
            continue  # never set, not being touched — nothing worth showing
        fields.append(
            {
                "label": FIELD_LABELS.get(f, f),
                "changed": changed,
                "current": current,
                "proposed": proposed if changed else None,
            }
        )
    return fields


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
        rows = []
        for r in requests:
            is_first = is_awaiting_first_review(r.user)
            fields = await _row_fields(session, r, is_first)
            rows.append({"req": r, "is_first_review": is_first, "fields": fields})
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
