"""Paraphrase job and candidate request schemas."""

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import GenerationProvider, Language, ParaphraseMode


class ParaphraseJobCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_question_id: str = Field(alias="sourceQuestionId")
    mode: ParaphraseMode = ParaphraseMode.FULL_QUESTION
    requested_count: int = Field(default=5, alias="requestedCount", ge=1, le=10)
    target_language: Language | None = Field(default=None, alias="targetLanguage")
    change_strength: str = Field(default="medium", alias="changeStrength", pattern="^(light|medium|strong)$")
    provider: GenerationProvider | None = None


class CandidateEdit(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    candidateStem: str = Field(min_length=15)
    option_a: str | None = Field(default=None, alias="optionA", min_length=1)
    option_b: str | None = Field(default=None, alias="optionB", min_length=1)
    option_c: str | None = Field(default=None, alias="optionC", min_length=1)
    option_d: str | None = Field(default=None, alias="optionD", min_length=1)


class ReviewRequest(BaseModel):
    reviewerNotes: str | None = None
