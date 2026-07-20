import csv
import io
from datetime import UTC, datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord
from app.models.enums import PriorExperience
from app.models.survey import Survey, SurveyAnswer, SurveyQuestion, SurveyResponse
from app.models.user import User


async def get_active_required_survey(session: AsyncSession) -> Survey | None:
    """The survey currently gating community stats for brand-new runners —
    at most one is meaningfully "the" required survey at a time; if an admin
    somehow leaves more than one flagged, the most recently created wins."""
    result = await session.scalar(
        select(Survey)
        .where(Survey.is_active.is_(True), Survey.is_required_for_access.is_(True))
        .order_by(Survey.id.desc())
    )
    return result


async def _has_any_attendance(session: AsyncSession, runner_id: int) -> bool:
    return bool(
        await session.scalar(
            select(exists().where(AttendanceRecord.runner_id == runner_id))
        )
    )


async def _has_completed(session: AsyncSession, survey_id: int, runner_id: int) -> bool:
    return bool(
        await session.scalar(
            select(
                exists().where(
                    SurveyResponse.survey_id == survey_id,
                    SurveyResponse.runner_id == runner_id,
                )
            )
        )
    )


async def stats_locked_pending_survey(session: AsyncSession, runner: User) -> bool:
    """Whether `runner` should stay locked out of community stats pending the
    newbie survey — True from the moment they report never having run with
    us before (see User.prior_experience) until they've completed the
    active required survey, with no exception for "haven't run yet": seeing
    the rating before your first DX and survey would skip the whole point of
    the gate. Contrast with survey_required_for, which additionally requires
    a tracked attendance — that one answers "can they fill it out right
    now", this one answers "should they still be locked"."""
    if runner.prior_experience != PriorExperience.never:
        return False
    survey = await get_active_required_survey(session)
    if survey is None:
        return False
    return not await _has_completed(session, survey.id, runner.id)


async def survey_required_for(session: AsyncSession, runner: User) -> Survey | None:
    """The survey this runner can fill out right now, or None. Only ever
    applies to runners who self-reported never having run with the
    community before (see User.prior_experience — only asked at signup for
    new accounts) *and* who've since logged their first tracked attendance
    ("first DX") — before that there's nothing to survey them about yet
    (they haven't run), so GET /surveys/active has nothing to hand back even
    though stats_locked_pending_survey is already True."""
    if runner.prior_experience != PriorExperience.never:
        return None
    survey = await get_active_required_survey(session)
    if survey is None:
        return None
    if not await _has_any_attendance(session, runner.id):
        return None
    if await _has_completed(session, survey.id, runner.id):
        return None
    return survey


async def submit_response(
    session: AsyncSession, survey: Survey, runner: User, answers: dict[int, str]
) -> SurveyResponse:
    """Record `runner`'s answers for `survey`. `answers` maps question_id ->
    text value; questions marked `required` must have a non-blank entry —
    raises ValueError naming the first one missing, so the caller can show a
    useful error instead of silently dropping the submission."""
    if await _has_completed(session, survey.id, runner.id):
        raise ValueError("Вы уже отправляли ответы на эту анкету")

    for question in survey.questions:
        if question.required and not (answers.get(question.id) or "").strip():
            raise ValueError(f"Ответ на вопрос «{question.prompt}» обязателен")

    response = SurveyResponse(
        survey_id=survey.id, runner_id=runner.id, submitted_at=datetime.now(UTC)
    )
    session.add(response)
    await session.flush()
    for question in survey.questions:
        value = (answers.get(question.id) or "").strip()
        if not value:
            continue
        session.add(SurveyAnswer(response_id=response.id, question_id=question.id, value=value))
    await session.flush()
    return response


async def export_responses_csv(session: AsyncSession, survey: Survey) -> str:
    """`;`-delimited, one row per response, one column per question (in
    survey order) plus runner name/email and submission time — matches the
    delimiter convention used by the other CSV import/export flows."""
    questions = list(survey.questions)
    responses = list(
        await session.scalars(
            select(SurveyResponse)
            .where(SurveyResponse.survey_id == survey.id)
            .order_by(SurveyResponse.submitted_at)
        )
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        ["runner_name", "runner_email", "submitted_at"] + [q.prompt for q in questions]
    )
    for response in responses:
        runner = await session.get(User, response.runner_id)
        answers = {
            a.question_id: a.value
            for a in await session.scalars(
                select(SurveyAnswer).where(SurveyAnswer.response_id == response.id)
            )
        }
        row = [
            f"{runner.first_name} {runner.last_name}" if runner else "",
            runner.email if runner and not runner.is_guest else "",
            response.submitted_at.isoformat(),
        ]
        row.extend(answers.get(q.id, "") for q in questions)
        writer.writerow(row)
    return buffer.getvalue()


async def question_answer_pairs(
    session: AsyncSession, response: SurveyResponse, questions: list[SurveyQuestion]
) -> list[tuple[SurveyQuestion, str]]:
    """(question, answer text) pairs in survey order, for rendering one
    response — blank string for a question the runner skipped."""
    answers = {
        a.question_id: a.value
        for a in await session.scalars(
            select(SurveyAnswer).where(SurveyAnswer.response_id == response.id)
        )
    }
    return [(q, answers.get(q.id, "")) for q in questions]
