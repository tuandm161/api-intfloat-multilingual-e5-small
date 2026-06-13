"""Shared enums used across all development phases."""

from enum import StrEnum


class QuestionType(StrEnum):
    ORIGINAL = "ORIGINAL"
    PARAPHRASE = "PARAPHRASE"


class QuestionStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class ParaphraseJobStatus(StrEnum):
    CREATED = "CREATED"
    GENERATING = "GENERATING"
    GENERATED = "GENERATED"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CandidateStatus(StrEnum):
    GENERATED = "GENERATED"
    VALIDATED = "VALIDATED"
    NEED_REVIEW = "NEED_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SAVED = "SAVED"


class CandidateLabel(StrEnum):
    GOOD = "GOOD"
    NEED_REVIEW = "NEED_REVIEW"
    REJECTED = "REJECTED"


class ParaphraseMode(StrEnum):
    STEM_ONLY = "STEM_ONLY"


class Language(StrEnum):
    vi = "vi"
    en = "en"
    bilingual = "bilingual"


class GenerationProvider(StrEnum):
    mock = "mock"
    api = "api"
    local = "local"


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    DUPLICATE_RESOURCE = "DUPLICATE_RESOURCE"
    GENERATION_FAILED = "GENERATION_FAILED"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    VECTOR_INDEX_FAILED = "VECTOR_INDEX_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
