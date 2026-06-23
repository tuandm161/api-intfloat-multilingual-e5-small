"""Document ingestion and generated-question request schemas."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentQuestionJobCreate(BaseModel):
    questions_per_chunk: int = Field(default=3, alias="questionsPerChunk", ge=1, le=5)


class DocumentQuestionCandidateEdit(BaseModel):
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
    source_excerpt: str | None = Field(default=None, alias="sourceExcerpt")

    @field_validator("correct_answer")
    @classmethod
    def validate_correct_answer(cls, value: str) -> str:
        value = value.upper()
        if value not in {"A", "B", "C", "D"}:
            raise ValueError("correctAnswer must be A, B, C, or D")
        return value


class DocumentReviewRequest(BaseModel):
    reviewerNotes: str | None = None
