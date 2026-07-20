from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.admin.tools_common import get_tools_user, login_redirect, templates
from app.core.db import SessionLocal
from app.models.enums import UserRole
from app.models.survey import Survey, SurveyQuestion, SurveyResponse
from app.models.user import User
from app.services.survey_service import export_responses_csv, question_answer_pairs

router = APIRouter(prefix="/admin-tools", tags=["admin-surveys"], include_in_schema=False)


async def _require_admin(request: Request) -> User | None:
    """Surveys are Admin-only, same as CSV import/moderation — organizers
    don't manage them."""
    user = await get_tools_user(request)
    if user is None or user.role != UserRole.admin:
        return None
    return user


@router.get("/surveys", response_class=HTMLResponse, response_model=None)
async def surveys_list(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        surveys = list(await session.scalars(select(Survey).order_by(Survey.id.desc())))
        count_rows = await session.execute(
            select(SurveyResponse.survey_id, func.count(SurveyResponse.id)).group_by(
                SurveyResponse.survey_id
            )
        )
        counts: dict[int, int] = {survey_id: count for survey_id, count in count_rows}
    return templates.TemplateResponse(
        request,
        "surveys_list.html",
        {"active": "surveys", "tools_user": user, "surveys": surveys, "counts": counts},
    )


@router.get("/surveys/new", response_class=HTMLResponse, response_model=None)
async def survey_new_form(request: Request) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    return templates.TemplateResponse(
        request, "survey_form.html", {"active": "surveys", "tools_user": user, "survey": None}
    )


@router.post("/surveys/new", response_model=None)
async def survey_new_submit(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    is_required_for_access: bool = Form(False),
) -> RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        if is_required_for_access:
            await _unset_other_required_surveys(session, exclude_id=None)
        survey = Survey(
            title=title,
            description=description or None,
            is_required_for_access=is_required_for_access,
            created_by=user.id,
        )
        session.add(survey)
        await session.commit()
        await session.refresh(survey)
    return RedirectResponse(f"/admin-tools/surveys/{survey.id}/edit?flash=Анкета создана", 303)


async def _unset_other_required_surveys(session: AsyncSession, exclude_id: int | None) -> None:
    """At most one survey is meaningfully "the" required one at a time —
    turning this on for one turns it off everywhere else, so the admin
    never has to remember to do that themselves."""
    stmt = select(Survey).where(Survey.is_required_for_access.is_(True))
    if exclude_id is not None:
        stmt = stmt.where(Survey.id != exclude_id)
    others = list(await session.scalars(stmt))
    for other in others:
        other.is_required_for_access = False


@router.get("/surveys/{survey_id}/edit", response_class=HTMLResponse, response_model=None)
async def survey_edit_form(request: Request, survey_id: int) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        survey = await session.get(
            Survey, survey_id, options=[selectinload(Survey.questions)]
        )
        if survey is None:
            return RedirectResponse("/admin-tools/surveys", status_code=303)
    flash = request.query_params.get("flash")
    return templates.TemplateResponse(
        request,
        "survey_form.html",
        {"active": "surveys", "tools_user": user, "survey": survey, "flash": flash},
    )


@router.post("/surveys/{survey_id}/edit", response_model=None)
async def survey_edit_submit(
    request: Request,
    survey_id: int,
    title: str = Form(...),
    description: str = Form(""),
    is_required_for_access: bool = Form(False),
    is_active: bool = Form(False),
) -> RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        survey = await session.get(Survey, survey_id)
        if survey is None:
            return RedirectResponse("/admin-tools/surveys", status_code=303)
        if is_required_for_access and not survey.is_required_for_access:
            await _unset_other_required_surveys(session, exclude_id=survey.id)
        survey.title = title
        survey.description = description or None
        survey.is_required_for_access = is_required_for_access
        survey.is_active = is_active
        await session.commit()
    return RedirectResponse(f"/admin-tools/surveys/{survey_id}/edit?flash=Сохранено", 303)


@router.post("/surveys/{survey_id}/questions/new", response_model=None)
async def survey_question_add(
    request: Request,
    survey_id: int,
    prompt: str = Form(...),
    required: bool = Form(False),
) -> RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        survey = await session.get(Survey, survey_id, options=[selectinload(Survey.questions)])
        if survey is None:
            return RedirectResponse("/admin-tools/surveys", status_code=303)
        next_position = max((q.position for q in survey.questions), default=-1) + 1
        session.add(
            SurveyQuestion(
                survey_id=survey.id, position=next_position, prompt=prompt, required=required
            )
        )
        await session.commit()
    return RedirectResponse(f"/admin-tools/surveys/{survey_id}/edit?flash=Вопрос добавлен", 303)


@router.post("/surveys/{survey_id}/questions/{question_id}/delete", response_model=None)
async def survey_question_delete(
    request: Request, survey_id: int, question_id: int
) -> RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        question = await session.get(SurveyQuestion, question_id)
        if question is not None and question.survey_id == survey_id:
            await session.delete(question)
            await session.commit()
    return RedirectResponse(f"/admin-tools/surveys/{survey_id}/edit?flash=Вопрос удалён", 303)


@router.post("/surveys/{survey_id}/questions/{question_id}/move", response_model=None)
async def survey_question_move(
    request: Request, survey_id: int, question_id: int, direction: str = Form(...)
) -> RedirectResponse:
    """Swap this question's position with its neighbor — the simplest
    reorder UI that works with plain forms/page reloads (no drag-and-drop)."""
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        survey = await session.get(Survey, survey_id, options=[selectinload(Survey.questions)])
        if survey is None:
            return RedirectResponse("/admin-tools/surveys", status_code=303)
        questions = survey.questions
        idx = next((i for i, q in enumerate(questions) if q.id == question_id), None)
        if idx is not None:
            neighbor_idx = idx - 1 if direction == "up" else idx + 1
            if 0 <= neighbor_idx < len(questions):
                questions[idx].position, questions[neighbor_idx].position = (
                    questions[neighbor_idx].position,
                    questions[idx].position,
                )
                await session.commit()
    return RedirectResponse(f"/admin-tools/surveys/{survey_id}/edit", 303)


@router.get("/surveys/{survey_id}/responses", response_class=HTMLResponse, response_model=None)
async def survey_responses(request: Request, survey_id: int) -> HTMLResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        survey = await session.get(Survey, survey_id, options=[selectinload(Survey.questions)])
        if survey is None:
            return RedirectResponse("/admin-tools/surveys", status_code=303)
        responses = list(
            await session.scalars(
                select(SurveyResponse)
                .where(SurveyResponse.survey_id == survey_id)
                .order_by(SurveyResponse.submitted_at.desc())
            )
        )
        runners = {
            u.id: u
            for u in await session.scalars(
                select(User).where(User.id.in_([r.runner_id for r in responses]))
            )
        }
        rows = [
            {
                "response": r,
                "runner": runners.get(r.runner_id),
                "answers": await question_answer_pairs(session, r, survey.questions),
            }
            for r in responses
        ]
    return templates.TemplateResponse(
        request,
        "survey_responses.html",
        {"active": "surveys", "tools_user": user, "survey": survey, "rows": rows},
    )


@router.get("/surveys/{survey_id}/responses/export", response_model=None)
async def survey_responses_export(
    request: Request, survey_id: int
) -> PlainTextResponse | RedirectResponse:
    user = await _require_admin(request)
    if user is None:
        return login_redirect()
    async with SessionLocal() as session:
        survey = await session.get(Survey, survey_id, options=[selectinload(Survey.questions)])
        if survey is None:
            return RedirectResponse("/admin-tools/surveys", status_code=303)
        csv_text = await export_responses_csv(session, survey)
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="survey-{survey_id}-responses.csv"'
        },
    )
