import json
from typing import Any

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.admin.tools_common import (
    can_manage_contest,
    combine_local_datetime,
    get_tools_user,
    login_redirect,
    require_permission,
    templates,
)
from app.core.db import SessionLocal
from app.core.timezone import now_msk
from app.models.contest import Contest, ContestEntry, ContestField
from app.models.enums import ContestFieldType, ModerationStatus, StaffPermission, UserRole
from app.models.user import User
from app.services import contest_service
from app.services.media_service import (
    FileTooLargeError,
    InvalidFileTypeError,
    delete_media,
    save_image,
)
from app.services.support_service import create_staff_ticket

router = APIRouter(prefix="/admin-tools", tags=["admin-contests"])


def _parse_fields(raw: str) -> list[dict[str, Any]]:
    """The constructor's field list arrives as one hidden JSON field, same
    "whole list in one hidden input" shape as a group's pace_segments —
    see app.admin.tools_groups._parse_pace_segments."""
    raw = raw.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        field_type = str(item.get("field_type") or "text")
        if field_type not in ContestFieldType.__members__:
            field_type = "text"
        raw_options = item.get("options")
        options = (
            [o.strip()[:255] for o in raw_options if isinstance(o, str) and o.strip()]
            if field_type == "multi_select" and isinstance(raw_options, list)
            else None
        )
        out.append(
            {
                "id": item.get("id"),
                "label": label[:255],
                "description": (str(item.get("description") or "").strip()[:1000] or None),
                "field_type": field_type,
                "required": bool(item.get("required", True)),
                "visible_to_voters": bool(item.get("visible_to_voters", True)),
                "options": options or None,
            }
        )
    return out


async def _sync_fields(session: AsyncSession, contest: Contest, raw: str) -> None:
    parsed = _parse_fields(raw)
    existing = {
        f.id: f
        for f in await session.scalars(
            select(ContestField).where(ContestField.contest_id == contest.id)
        )
    }
    keep_ids: set[int] = set()
    for position, item in enumerate(parsed):
        field = existing.get(item["id"]) if item["id"] else None
        if field is not None:
            keep_ids.add(field.id)
        else:
            field = ContestField(contest_id=contest.id)
            session.add(field)
        field.position = position
        field.label = item["label"]
        field.description = item["description"]
        field.field_type = ContestFieldType(item["field_type"])
        field.required = item["required"]
        field.visible_to_voters = item["visible_to_voters"]
        field.options = item["options"]
    for field_id, field in existing.items():
        if field_id not in keep_ids:
            await session.delete(field)


@router.get("/contests", response_class=HTMLResponse, response_model=None)
async def contests_list(request: Request) -> HTMLResponse | RedirectResponse:
    user = await require_permission(request, StaffPermission.contests)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        stmt = select(Contest).order_by(Contest.id.desc())
        if user.role != UserRole.admin:
            stmt = stmt.where(Contest.created_by == user.id)
        contests = list(await session.scalars(stmt))
        phases = {
            c.id: contest_service.PHASE_LABELS_RU[contest_service.contest_phase(c)]
            for c in contests
        }
    return templates.TemplateResponse(
        request,
        "contests_list.html",
        {
            "active": "contests",
            "tools_user": user,
            "contests": contests,
            "phases": phases,
            "flash": request.query_params.get("flash"),
        },
    )


@router.get("/contests/new", response_class=HTMLResponse, response_model=None)
async def contest_new_form(request: Request) -> HTMLResponse | RedirectResponse:
    user = await require_permission(request, StaffPermission.contests)
    if user is None:
        return login_redirect()
    return templates.TemplateResponse(
        request,
        "contest_form.html",
        {"active": "contests", "tools_user": user, "contest": None, "fields": []},
    )


def _parse_max_entries(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


@router.post("/contests/new", response_model=None)
async def contest_new_submit(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    submissions_open_at: str = Form(""),
    submissions_close_at: str = Form(""),
    voting_open_at: str = Form(""),
    voting_close_at: str = Form(""),
    votes_visible_live: bool = Form(False),
    max_entries_per_runner: str = Form(""),
    fields: str = Form(""),
) -> RedirectResponse:
    user = await require_permission(request, StaffPermission.contests)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        contest = Contest(
            title=title,
            description=description or None,
            created_by=user.id,
            submissions_open_at=combine_local_datetime(submissions_open_at),
            submissions_close_at=combine_local_datetime(submissions_close_at),
            voting_open_at=combine_local_datetime(voting_open_at),
            voting_close_at=combine_local_datetime(voting_close_at),
            votes_visible_live=votes_visible_live,
            max_entries_per_runner=_parse_max_entries(max_entries_per_runner),
        )
        session.add(contest)
        await session.flush()
        await _sync_fields(session, contest, fields)
        await session.commit()
        await session.refresh(contest)
    return RedirectResponse(f"/admin-tools/contests/{contest.id}/edit?flash=Конкурс создан", 303)


async def _get_owned_contest(session: AsyncSession, user: User, contest_id: int) -> Contest | None:
    contest = await session.get(Contest, contest_id)
    if contest is None or not can_manage_contest(user, contest):
        return None
    return contest


async def _require_entries_access(request: Request) -> User | None:
    """Entry moderation is reachable with either the broad, delegable-to-
    anyone `contests_review` (any contest, not just your own — same rule
    results_review already uses, see staff_attention_service) or `contests`
    (the contest's own creator/admin, checked per-contest below)."""
    user = await get_tools_user(request)
    if user is None:
        return None
    perms = user.granted_permissions
    if StaffPermission.contests_review in perms or StaffPermission.contests in perms:
        return user
    return None


async def _get_contest_for_moderation(
    session: AsyncSession, user: User, contest_id: int
) -> Contest | None:
    contest = await session.get(Contest, contest_id)
    if contest is None:
        return None
    if StaffPermission.contests_review in user.granted_permissions:
        return contest
    return contest if can_manage_contest(user, contest) else None


@router.get("/contests/{contest_id}/edit", response_class=HTMLResponse, response_model=None)
async def contest_edit_form(request: Request, contest_id: int) -> HTMLResponse | RedirectResponse:
    user = await require_permission(request, StaffPermission.contests)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        contest = await _get_owned_contest(session, user, contest_id)
        if contest is None:
            return RedirectResponse("/admin-tools/contests", status_code=303)
        fields = list(
            await session.scalars(
                select(ContestField)
                .where(ContestField.contest_id == contest_id)
                .order_by(ContestField.position)
            )
        )
        phase = contest_service.contest_phase(contest)
    return templates.TemplateResponse(
        request,
        "contest_form.html",
        {
            "active": "contests",
            "tools_user": user,
            "contest": contest,
            "fields": fields,
            "phase": contest_service.PHASE_LABELS_RU[phase],
            "flash": request.query_params.get("flash"),
        },
    )


@router.post("/contests/{contest_id}/edit", response_model=None)
async def contest_edit_submit(
    request: Request,
    contest_id: int,
    title: str = Form(...),
    description: str = Form(""),
    submissions_open_at: str = Form(""),
    submissions_close_at: str = Form(""),
    voting_open_at: str = Form(""),
    voting_close_at: str = Form(""),
    votes_visible_live: bool = Form(False),
    max_entries_per_runner: str = Form(""),
    fields: str = Form(""),
) -> RedirectResponse:
    user = await require_permission(request, StaffPermission.contests)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        contest = await _get_owned_contest(session, user, contest_id)
        if contest is None:
            return RedirectResponse("/admin-tools/contests", status_code=303)
        contest.title = title
        contest.description = description or None
        contest.submissions_open_at = combine_local_datetime(submissions_open_at)
        contest.submissions_close_at = combine_local_datetime(submissions_close_at)
        contest.voting_open_at = combine_local_datetime(voting_open_at)
        contest.voting_close_at = combine_local_datetime(voting_close_at)
        contest.votes_visible_live = votes_visible_live
        contest.max_entries_per_runner = _parse_max_entries(max_entries_per_runner)
        await _sync_fields(session, contest, fields)
        await session.commit()
    return RedirectResponse(
        f"/admin-tools/contests/{contest_id}/edit?flash=Сохранено", status_code=303
    )


@router.post("/contests/{contest_id}/cover", response_model=None)
async def contest_cover_upload(
    request: Request, contest_id: int, file: UploadFile
) -> RedirectResponse:
    user = await require_permission(request, StaffPermission.contests)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        contest = await _get_owned_contest(session, user, contest_id)
        if contest is None:
            return RedirectResponse("/admin-tools/contests", status_code=303)
        try:
            path = await save_image(file, "contest_covers")
        except (FileTooLargeError, InvalidFileTypeError) as exc:
            return RedirectResponse(
                f"/admin-tools/contests/{contest_id}/edit?flash_error={exc}", 303
            )
        delete_media(contest.cover_image)
        contest.cover_image = path
        await session.commit()
    return RedirectResponse(
        f"/admin-tools/contests/{contest_id}/edit?flash=Заставка обновлена", 303
    )


@router.post("/contests/{contest_id}/publish", response_model=None)
async def contest_publish(request: Request, contest_id: int) -> RedirectResponse:
    user = await require_permission(request, StaffPermission.contests)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        contest = await _get_owned_contest(session, user, contest_id)
        if contest is None:
            return RedirectResponse("/admin-tools/contests", status_code=303)
        contest.is_published = True
        await session.commit()
    return RedirectResponse(f"/admin-tools/contests/{contest_id}/edit?flash=Конкурс запущен", 303)


@router.post("/contests/{contest_id}/unpublish", response_model=None)
async def contest_unpublish(request: Request, contest_id: int) -> RedirectResponse:
    user = await require_permission(request, StaffPermission.contests)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        contest = await _get_owned_contest(session, user, contest_id)
        if contest is None:
            return RedirectResponse("/admin-tools/contests", status_code=303)
        contest.is_published = False
        await session.commit()
    return RedirectResponse(
        f"/admin-tools/contests/{contest_id}/edit?flash=Конкурс снят с публикации", 303
    )


# --- moderation -----------------------------------------------------


@router.get("/contest-entries", response_class=HTMLResponse, response_model=None)
async def contest_entries_inbox(request: Request) -> HTMLResponse | RedirectResponse:
    """Cross-contest pending-entries inbox — reachable with just
    `contests_review` (no `contests` needed), unlike the per-contest /entries
    page below which also accepts a contest's own owner. Mirrors
    tools_results.py's cross-event /results inbox."""
    user = await require_permission(request, StaffPermission.contests_review)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        entries = list(
            await session.scalars(
                select(ContestEntry)
                .where(ContestEntry.status == ModerationStatus.pending)
                .options(
                    selectinload(ContestEntry.runner),
                    selectinload(ContestEntry.values),
                    selectinload(ContestEntry.contest).selectinload(Contest.fields),
                )
                .order_by(ContestEntry.submitted_at.desc())
            )
        )
        values_by_entry = {e.id: {v.field_id: v.value for v in e.values} for e in entries}
    return templates.TemplateResponse(
        request,
        "contest_entries_inbox.html",
        {
            "active": "contest-entries",
            "tools_user": user,
            "entries": entries,
            "values_by_entry": values_by_entry,
            "flash": request.query_params.get("flash"),
        },
    )


@router.get("/contests/{contest_id}/entries", response_class=HTMLResponse, response_model=None)
async def contest_entries(request: Request, contest_id: int) -> HTMLResponse | RedirectResponse:
    user = await _require_entries_access(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        contest = await _get_contest_for_moderation(session, user, contest_id)
        if contest is None:
            # Not /admin-tools/contests — a contests_review-only reviewer
            # (no `contests`) can't reach that list, so bounce somewhere
            # everyone with entries access can actually load.
            return RedirectResponse("/admin-tools", status_code=303)
        fields = list(
            await session.scalars(
                select(ContestField)
                .where(ContestField.contest_id == contest_id)
                .order_by(ContestField.position)
            )
        )
        entries = list(
            await session.scalars(
                select(ContestEntry)
                .where(ContestEntry.contest_id == contest_id)
                .options(selectinload(ContestEntry.values), selectinload(ContestEntry.runner))
                .order_by(ContestEntry.submitted_at.desc())
            )
        )
        values_by_entry = {e.id: {v.field_id: v.value for v in e.values} for e in entries}
    return templates.TemplateResponse(
        request,
        "contest_entries.html",
        {
            "active": "contest-entries",
            "tools_user": user,
            "contest": contest,
            "fields": fields,
            "entries": entries,
            "values_by_entry": values_by_entry,
            "flash": request.query_params.get("flash"),
        },
    )


def _entry_decision_message(entry: ContestEntry, contest: Contest, *, accepted: bool) -> str:
    lines = [
        f"Ваша заявка на конкурс «{contest.title}» "
        + ("принята и допущена к голосованию." if accepted else "отклонена."),
    ]
    if not accepted and entry.rejection_reason:
        lines += ["", f"Причина: {entry.rejection_reason}"]
        lines += ["", "Вы можете доработать и отправить заявку заново, пока приём открыт."]
    return "\n".join(lines)


@router.post("/contests/{contest_id}/entries/{entry_id}/approve", response_model=None)
async def approve_contest_entry(
    request: Request, contest_id: int, entry_id: int
) -> RedirectResponse:
    user = await _require_entries_access(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        contest = await _get_contest_for_moderation(session, user, contest_id)
        if contest is None:
            return RedirectResponse("/admin-tools", status_code=303)
        entry = await session.get(
            ContestEntry, entry_id, options=[selectinload(ContestEntry.runner)]
        )
        if entry is None or entry.contest_id != contest_id:
            return RedirectResponse(
                f"/admin-tools/contests/{contest_id}/entries?flash=Заявка не найдена", 303
            )
        entry.status = ModerationStatus.approved
        entry.rejection_reason = None
        if entry.runner is not None and not entry.runner.is_guest:
            await create_staff_ticket(
                session,
                recipient=entry.runner,
                admin=user,
                body=_entry_decision_message(entry, contest, accepted=True),
                email_subject="Итоги по заявке на конкурс — DАЙ ХАРD Чебоксары",
                email_kicker="Конкурсы",
                email_intro=f"По вашей заявке на конкурс «{contest.title}»:",
            )
        await session.commit()
    return RedirectResponse(f"/admin-tools/contests/{contest_id}/entries?flash=Заявка принята", 303)


@router.post("/contests/{contest_id}/entries/{entry_id}/reject", response_model=None)
async def reject_contest_entry(
    request: Request, contest_id: int, entry_id: int, reason: str = Form("")
) -> RedirectResponse:
    user = await _require_entries_access(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        contest = await _get_contest_for_moderation(session, user, contest_id)
        if contest is None:
            return RedirectResponse("/admin-tools", status_code=303)
        entry = await session.get(
            ContestEntry, entry_id, options=[selectinload(ContestEntry.runner)]
        )
        if entry is None or entry.contest_id != contest_id:
            return RedirectResponse(
                f"/admin-tools/contests/{contest_id}/entries?flash=Заявка не найдена", 303
            )
        if entry.status == ModerationStatus.rejected:
            return RedirectResponse(
                f"/admin-tools/contests/{contest_id}/entries?flash=Уже отклонена", 303
            )
        entry.status = ModerationStatus.rejected
        entry.rejection_reason = reason.strip() or None
        if entry.runner is not None and not entry.runner.is_guest:
            await create_staff_ticket(
                session,
                recipient=entry.runner,
                admin=user,
                body=_entry_decision_message(entry, contest, accepted=False),
                email_subject="Итоги по заявке на конкурс — DАЙ ХАРD Чебоксары",
                email_kicker="Конкурсы",
                email_intro=f"По вашей заявке на конкурс «{contest.title}»:",
            )
        await session.commit()
    return RedirectResponse(
        f"/admin-tools/contests/{contest_id}/entries?flash=Заявка отклонена, участник уведомлён",
        303,
    )


# --- results -----------------------------------------------------


@router.get("/contests/{contest_id}/results", response_class=HTMLResponse, response_model=None)
async def contest_results(request: Request, contest_id: int) -> HTMLResponse | RedirectResponse:
    user = await require_permission(request, StaffPermission.contests)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        contest = await _get_owned_contest(session, user, contest_id)
        if contest is None:
            return RedirectResponse("/admin-tools/contests", status_code=303)
        entries = list(
            await session.scalars(
                select(ContestEntry)
                .where(
                    ContestEntry.contest_id == contest_id,
                    ContestEntry.status == ModerationStatus.approved,
                )
                .options(selectinload(ContestEntry.runner))
            )
        )
        tally = await contest_service.vote_tally(session, contest_id)
        entries.sort(key=lambda e: (-(tally.get(e.id, 0)), e.id))
    return templates.TemplateResponse(
        request,
        "contest_results.html",
        {
            "active": "contests",
            "tools_user": user,
            "contest": contest,
            "entries": entries,
            "tally": tally,
            "flash": request.query_params.get("flash"),
        },
    )


@router.post("/contests/{contest_id}/results/{entry_id}/placement", response_model=None)
async def set_contest_placement(
    request: Request, contest_id: int, entry_id: int, placement: str = Form("")
) -> RedirectResponse:
    user = await require_permission(request, StaffPermission.contests)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        contest = await _get_owned_contest(session, user, contest_id)
        if contest is None:
            return RedirectResponse("/admin-tools/contests", status_code=303)
        entry = await session.get(ContestEntry, entry_id)
        if entry is None or entry.contest_id != contest_id:
            return RedirectResponse(
                f"/admin-tools/contests/{contest_id}/results?flash=Заявка не найдена", 303
            )
        value = placement.strip()
        await contest_service.set_placement(session, entry, int(value) if value else None)
        await session.commit()
    return RedirectResponse(f"/admin-tools/contests/{contest_id}/results", status_code=303)


@router.post("/contests/{contest_id}/results/publish", response_model=None)
async def publish_contest_results(request: Request, contest_id: int) -> RedirectResponse:
    user = await require_permission(request, StaffPermission.contests)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        contest = await _get_owned_contest(session, user, contest_id)
        if contest is None:
            return RedirectResponse("/admin-tools/contests", status_code=303)
        await contest_service.publish_results(session, contest, now=now_msk())
        await session.commit()
    return RedirectResponse(
        f"/admin-tools/contests/{contest_id}/results?flash=Итоги опубликованы", 303
    )
