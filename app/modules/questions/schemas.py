"""Question request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import Language, QuestionStatus, QuestionType


class QuestionCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    stem: str = Field(min_length=1)
    option_a: str = Field(alias="optionA", min_length=1)
    option_b: str = Field(alias="optionB", min_length=1)
    option_c: str = Field(alias="optionC", min_length=1)
    option_d: str = Field(alias="optionD", min_length=1)
    correct_answer: str = Field(alias="correctAnswer")
    explanation: str | None = None
    topic: str | None = None
    difficulty: str | None = None
    language: Language = Language.vi
    source_document: str | None = Field(default=None, alias="sourceDocument")
    question_type: QuestionType = Field(
        default=QuestionType.ORIGINAL, alias="questionType"
    )
    status: QuestionStatus = QuestionStatus.APPROVED
    parent_question_id: str | None = Field(default=None, alias="parentQuestionId")

    @field_validator("correct_answer")
    @classmethod
    def validate_correct_answer(cls, value: str) -> str:
        value = value.upper()
        if value not in {"A", "B", "C", "D"}:
            raise ValueError("correctAnswer must be A, B, C, or D")
        return value


class QuestionUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    stem: str | None = Field(default=None, min_length=1)
    option_a: str | None = Field(default=None, alias="optionA", min_length=1)
    option_b: str | None = Field(default=None, alias="optionB", min_length=1)
    option_c: str | None = Field(default=None, alias="optionC", min_length=1)
    option_d: str | None = Field(default=None, alias="optionD", min_length=1)
    correct_answer: str | None = Field(default=None, alias="correctAnswer")
    explanation: str | None = None
    topic: str | None = None
    difficulty: str | None = None
    language: Language | None = None
    source_document: str | None = Field(default=None, alias="sourceDocument")
    status: QuestionStatus | None = None

    @field_validator("correct_answer")
    @classmethod
    def validate_correct_answer(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.upper()
        if value not in {"A", "B", "C", "D"}:
            raise ValueError("correctAnswer must be A, B, C, or D")
        return value


class QuestionListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, alias="pageSize", ge=1, le=100)
    search: str | None = None
    topic: str | None = None
    status: QuestionStatus | None = None
    question_type: QuestionType | None = Field(default=None, alias="questionType")
    parent_question_id: str | None = Field(default=None, alias="parentQuestionId")


class QuestionDetail(BaseModel):
    id: str
    stem: str
    options: dict[str, str]
    correctAnswer: str
    explanation: str | None
    topic: str | None
    difficulty: str | None
    language: str
    sourceDocument: str | None
    questionType: str
    status: str
    parentQuestionId: str | None
    paraphraseCount: int
    createdAt: datetime
    updatedAt: datetime
