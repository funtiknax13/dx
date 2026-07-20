from pydantic import BaseModel, Field


class SurveyQuestionOut(BaseModel):
    id: int
    position: int
    prompt: str
    question_type: str
    required: bool


class SurveyOut(BaseModel):
    id: int
    title: str
    description: str | None
    questions: list[SurveyQuestionOut]


class SurveySubmitAnswer(BaseModel):
    question_id: int
    value: str = Field(default="", max_length=10_000)


class SurveySubmitRequest(BaseModel):
    answers: list[SurveySubmitAnswer]
