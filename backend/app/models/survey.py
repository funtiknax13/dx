from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import SurveyQuestionType


class Survey(Base, TimestampMixin):
    """An admin-editable questionnaire — e.g. the newbie feedback survey, or a
    future bonus-program survey. Multiple surveys can exist over time; only
    an active one with `is_required_for_access=True` gates community stats
    (see profile_completeness_service) — an admin toggles that per survey,
    optional ones (future bonus surveys) never block anything."""

    __tablename__ = "surveys"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_required_for_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    questions = relationship(
        "SurveyQuestion",
        back_populates="survey",
        cascade="all, delete-orphan",
        order_by="SurveyQuestion.position",
    )
    responses = relationship(
        "SurveyResponse", back_populates="survey", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return self.title


class SurveyQuestion(Base, TimestampMixin):
    __tablename__ = "survey_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    survey_id: Mapped[int] = mapped_column(
        ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # Every question in the first real survey is open text — the type exists
    # so a future survey can add choice-style questions without a schema
    # change, not because anything reads it yet beyond long_text.
    question_type: Mapped[SurveyQuestionType] = mapped_column(
        Enum(SurveyQuestionType, native_enum=False, length=20),
        default=SurveyQuestionType.long_text,
        nullable=False,
    )
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    survey = relationship("Survey", back_populates="questions")

    def __str__(self) -> str:
        return f"#{self.position + 1}: {self.prompt[:60]}"


class SurveyResponse(Base, TimestampMixin):
    """One runner's completed submission for one survey — all their answers
    hang off this via SurveyAnswer. One response per runner per survey."""

    __tablename__ = "survey_responses"
    __table_args__ = (UniqueConstraint("survey_id", "runner_id", name="uq_survey_response_runner"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    survey_id: Mapped[int] = mapped_column(
        ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    runner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Set when any staff member opens this survey's responses list — a
    # shared "team inbox" read state (not per-admin), same pattern as
    # SupportMessage.read_at. Drives the admin-tools nav badge.
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    survey = relationship("Survey", back_populates="responses")
    runner = relationship("User")
    answers = relationship(
        "SurveyAnswer", back_populates="response", cascade="all, delete-orphan"
    )

    def __str__(self) -> str:
        return f"response #{self.id} ({self.runner})"


class SurveyAnswer(Base, TimestampMixin):
    __tablename__ = "survey_answers"
    __table_args__ = (
        UniqueConstraint("response_id", "question_id", name="uq_survey_answer_question"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    response_id: Mapped[int] = mapped_column(
        ForeignKey("survey_responses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("survey_questions.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)

    response = relationship("SurveyResponse", back_populates="answers")
    question = relationship("SurveyQuestion")
