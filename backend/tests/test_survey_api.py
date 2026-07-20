import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import FinishStatus, ModerationStatus, PriorExperience, UserRole
from app.models.survey import Survey, SurveyQuestion
from tests.factories import make_attendance_with_result, make_event_group, make_user


async def _make_required_survey(session: AsyncSession, admin) -> Survey:
    survey = Survey(
        title="Newbie survey",
        is_required_for_access=True,
        is_active=True,
        created_by=admin.id,
    )
    session.add(survey)
    await session.flush()
    session.add(SurveyQuestion(survey_id=survey.id, position=0, prompt="Q1", required=True))
    await session.flush()
    return survey


@pytest.mark.asyncio
async def test_rating_locked_with_survey_required_reason(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-surveyapi1@example.com", UserRole.admin)
    org = await make_user(session, "org-surveyapi1@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-surveyapi1@example.com")
    runner.prior_experience = PriorExperience.never
    _, group = await make_event_group(session, org)
    await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.approved,
    )
    await _make_required_survey(session, admin)
    await session.commit()

    token = create_access_token(runner.id)
    resp = await client.get("/api/v1/rating", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert body["lock_reason"] == "survey_required"
    assert body["entries"] == []


@pytest.mark.asyncio
async def test_active_survey_endpoint_returns_survey_when_required(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-surveyapi2@example.com", UserRole.admin)
    org = await make_user(session, "org-surveyapi2@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-surveyapi2@example.com")
    runner.prior_experience = PriorExperience.never
    _, group = await make_event_group(session, org)
    await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.approved,
    )
    survey = await _make_required_survey(session, admin)
    await session.commit()

    token = create_access_token(runner.id)
    resp = await client.get("/api/v1/surveys/active", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body is not None
    assert body["id"] == survey.id
    assert len(body["questions"]) == 1


@pytest.mark.asyncio
async def test_active_survey_endpoint_returns_null_when_not_required(
    session: AsyncSession, client: AsyncClient
) -> None:
    runner = await make_user(session, "runner-surveyapi3@example.com")
    await session.commit()

    token = create_access_token(runner.id)
    resp = await client.get("/api/v1/surveys/active", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    assert resp.json() is None


@pytest.mark.asyncio
async def test_submit_survey_response_unlocks_stats(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-surveyapi4@example.com", UserRole.admin)
    org = await make_user(session, "org-surveyapi4@example.com", UserRole.organizer)
    runner = await make_user(session, "runner-surveyapi4@example.com")
    runner.prior_experience = PriorExperience.never
    _, group = await make_event_group(session, org)
    await make_attendance_with_result(
        session,
        group,
        runner,
        finish_status=FinishStatus.finished,
        moderation=ModerationStatus.approved,
    )
    survey = await _make_required_survey(session, admin)
    await session.commit()

    token = create_access_token(runner.id)
    headers = {"Authorization": f"Bearer {token}"}

    active = await client.get("/api/v1/surveys/active", headers=headers)
    question_id = active.json()["questions"][0]["id"]

    submit = await client.post(
        f"/api/v1/surveys/{survey.id}/responses",
        headers=headers,
        json={"answers": [{"question_id": question_id, "value": "My answer"}]},
    )
    assert submit.status_code == 201, submit.text

    rating = await client.get("/api/v1/rating", headers=headers)
    assert rating.json()["lock_reason"] is None


@pytest.mark.asyncio
async def test_submit_survey_response_rejects_missing_required_answer(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-surveyapi5@example.com", UserRole.admin)
    runner = await make_user(session, "runner-surveyapi5@example.com")
    survey = await _make_required_survey(session, admin)
    await session.commit()

    token = create_access_token(runner.id)
    resp = await client.post(
        f"/api/v1/surveys/{survey.id}/responses",
        headers={"Authorization": f"Bearer {token}"},
        json={"answers": []},
    )
    assert resp.status_code == 400
