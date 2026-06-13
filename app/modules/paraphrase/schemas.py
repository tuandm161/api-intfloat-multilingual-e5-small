"""Paraphrase job and candidate request schemas."""

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import GenerationProvider, Language, ParaphraseMode


class ParaphraseJobCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_question_id: str = Field(alias="sourceQuestionId")
    mode: ParaphraseMode = ParaphraseMode.STEM_ONLY
    requested_count: int = Field(default=5, alias="requestedCount", ge=1, le=10)
    target_language: Language | None = Field(default=None, alias="targetLanguage")
    change_strength: str = Field(default="medium", alias="changeStrength", pattern="^(light|medium|strong)$")
    provider: GenerationProvider = GenerationProvider.mock


class CandidateEdit(BaseModel):
    candidateStem: str = Field(min_length=15)


class ReviewRequest(BaseModel):
    reviewerNotes: str | None = None
