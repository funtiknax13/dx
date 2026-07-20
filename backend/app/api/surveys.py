from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.models.survey import Survey
from app.schemas.survey import SurveyOut, SurveyQuestionOut, SurveySubmitRequest
from app.services.survey_service import submit_response, survey_required_for

router = APIRouter(prefix="/surveys", tags=["surveys"])


def _to_out(survey: Survey) -> SurveyOut:
    return SurveyOut(
        id=survey.id,
        title=survey.title,
        description=survey.description,
        questions=[
            SurveyQuestionOut(
                id=q.id,
                position=q.position,
                prompt=q.prompt,
                question_type=q.question_type.value,
                required=q.required,
            )
            for q in survey.questions
        ],
    )


@router.get("/active", response_model=SurveyOut | None)
async def active_survey(user: CurrentUser, session: SessionDep) -> SurveyOut | None:
    """The survey `user` still needs to complete before their stats unlock —
    None if nothing's required of them right now (see
    survey_service.survey_required_for for exactly when that is)."""
    survey = await survey_required_for(session, user)
    if survey is None:
        return None
    # `survey` is already in the session's identity map from
    # survey_required_for's own query, so a second session.get(..., options=
    # [selectinload(...)]) would silently return the cached instance without
    # applying the new eager-load — refresh the relationship explicitly
    # instead, which always re-fetches it.
    await session.refresh(survey, attribute_names=["questions"])
    return _to_out(survey)


@router.post("/{survey_id}/responses", status_code=status.HTTP_201_CREATED)
async def submit_survey_response(
    survey_id: int, payload: SurveySubmitRequest, user: CurrentUser, session: SessionDep
) -> dict[str, str]:
    survey = await session.get(Survey, survey_id, options=[selectinload(Survey.questions)])
    if survey is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Survey not found")

    answers = {a.question_id: a.value for a in payload.answers}
    try:
        await submit_response(session, survey, user, answers)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return {"detail": "Ответы сохранены, спасибо!"}
