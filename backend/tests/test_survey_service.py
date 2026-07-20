import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import FinishStatus, ModerationStatus, PriorExperience, UserRole
from app.models.survey import Survey, SurveyAnswer, SurveyQuestion
from app.services.survey_service import (
    export_responses_csv,
    submit_response,
    survey_required_for,
)
from tests.factories import make_attendance_with_result, make_event_group, make_user


async def _make_survey(
    session: AsyncSession, admin, *, required: bool = True, active: bool = True
) -> Survey:
    survey = Survey(
        title="Newbie survey",
        description=None,
        is_required_for_access=required,
        is_active=active,
        created_by=admin.id,
    )
    session.add(survey)
    await session.flush()
    session.add(SurveyQuestion(survey_id=survey.id, position=0, prompt="Q1", required=True))
    session.add(SurveyQuestion(survey_id=survey.id, position=1, prompt="Q2", required=False))
    await session.flush()
    await session.refresh(survey, attribute_names=["questions"])
    return survey


@pytest.mark.asyncio
async def test_survey_not_required_when_prior_experience_not_never(
    session: AsyncSession,
) -> None:
    admin = await make_user(session, "admin-survey1@example.com", UserRole.admin)
    runner = await make_user(session, "runner-survey1@example.com")
    runner.prior_experience = PriorExperience.multiple
    org = await make_user(session, "org-survey1@example.com", UserRole.organizer)
    _, group = await make_event_group(session, org)
    await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.approved,
    )
    await _make_survey(session, admin)
    await session.commit()

    assert await survey_required_for(session, runner) is None


@pytest.mark.asyncio
async def test_survey_not_required_without_any_active_required_survey(
    session: AsyncSession,
) -> None:
    runner = await make_user(session, "runner-survey2@example.com")
    runner.prior_experience = PriorExperience.never
    org = await make_user(session, "org-survey2@example.com", UserRole.organizer)
    _, group = await make_event_group(session, org)
    await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.approved,
    )
    await session.commit()

    assert await survey_required_for(session, runner) is None


@pytest.mark.asyncio
async def test_survey_not_required_before_first_attendance(session: AsyncSession) -> None:
    admin = await make_user(session, "admin-survey3@example.com", UserRole.admin)
    runner = await make_user(session, "runner-survey3@example.com")
    runner.prior_experience = PriorExperience.never
    await _make_survey(session, admin)
    await session.commit()

    assert await survey_required_for(session, runner) is None


@pytest.mark.asyncio
async def test_survey_required_when_all_conditions_met(session: AsyncSession) -> None:
    admin = await make_user(session, "admin-survey4@example.com", UserRole.admin)
    runner = await make_user(session, "runner-survey4@example.com")
    runner.prior_experience = PriorExperience.never
    org = await make_user(session, "org-survey4@example.com", UserRole.organizer)
    _, group = await make_event_group(session, org)
    await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.approved,
    )
    survey = await _make_survey(session, admin)
    await session.commit()

    required = await survey_required_for(session, runner)
    assert required is not None
    assert required.id == survey.id


@pytest.mark.asyncio
async def test_survey_not_required_once_completed(session: AsyncSession) -> None:
    admin = await make_user(session, "admin-survey5@example.com", UserRole.admin)
    runner = await make_user(session, "runner-survey5@example.com")
    runner.prior_experience = PriorExperience.never
    org = await make_user(session, "org-survey5@example.com", UserRole.organizer)
    _, group = await make_event_group(session, org)
    await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.approved,
    )
    survey = await _make_survey(session, admin)
    await session.commit()

    await submit_response(session, survey, runner, {survey.questions[0].id: "Answer"})
    await session.commit()

    assert await survey_required_for(session, runner) is None


@pytest.mark.asyncio
async def test_submit_response_requires_required_questions(session: AsyncSession) -> None:
    admin = await make_user(session, "admin-survey6@example.com", UserRole.admin)
    runner = await make_user(session, "runner-survey6@example.com")
    survey = await _make_survey(session, admin)
    await session.commit()

    with pytest.raises(ValueError, match="обязателен"):
        await submit_response(session, survey, runner, {})


@pytest.mark.asyncio
async def test_submit_response_saves_answers_and_skips_blank_optional(
    session: AsyncSession,
) -> None:
    admin = await make_user(session, "admin-survey7@example.com", UserRole.admin)
    runner = await make_user(session, "runner-survey7@example.com")
    survey = await _make_survey(session, admin)
    await session.commit()

    q1, q2 = survey.questions[0], survey.questions[1]
    response = await submit_response(
        session, survey, runner, {q1.id: "Required answer", q2.id: "  "}
    )
    await session.commit()

    answers = list(
        await session.scalars(select(SurveyAnswer).where(SurveyAnswer.response_id == response.id))
    )
    assert len(answers) == 1
    assert answers[0].question_id == q1.id
    assert answers[0].value == "Required answer"


@pytest.mark.asyncio
async def test_submit_response_rejects_duplicate_submission(session: AsyncSession) -> None:
    admin = await make_user(session, "admin-survey8@example.com", UserRole.admin)
    runner = await make_user(session, "runner-survey8@example.com")
    survey = await _make_survey(session, admin)
    await session.commit()

    await submit_response(session, survey, runner, {survey.questions[0].id: "Answer"})
    await session.commit()

    with pytest.raises(ValueError, match="уже отправляли"):
        await submit_response(session, survey, runner, {survey.questions[0].id: "Again"})


@pytest.mark.asyncio
async def test_export_responses_csv_includes_header_and_answers(session: AsyncSession) -> None:
    admin = await make_user(session, "admin-survey9@example.com", UserRole.admin)
    runner = await make_user(session, "runner-survey9@example.com")
    survey = await _make_survey(session, admin)
    await session.commit()

    await submit_response(session, survey, runner, {survey.questions[0].id: "First answer"})
    await session.commit()
    await session.refresh(survey, attribute_names=["questions"])

    csv_text = await export_responses_csv(session, survey)
    lines = csv_text.strip().splitlines()
    assert lines[0] == "runner_name;runner_email;submitted_at;Q1;Q2"
    assert "First answer" in lines[1]
    assert "runner-survey9@example.com" in lines[1]
