from app.core.enums import (
    CandidateLabel,
    CandidateStatus,
    GenerationProvider,
    Language,
    ParaphraseJobStatus,
    ParaphraseMode,
    QuestionStatus,
    QuestionType,
)


def test_shared_enum_values_match_contract() -> None:
    assert [item.value for item in QuestionType] == ["ORIGINAL", "PARAPHRASE"]
    assert [item.value for item in QuestionStatus] == [
        "DRAFT",
        "APPROVED",
        "REJECTED",
        "ARCHIVED",
    ]
    assert [item.value for item in ParaphraseJobStatus] == [
        "CREATED",
        "GENERATING",
        "GENERATED",
        "VALIDATING",
        "COMPLETED",
        "FAILED",
    ]
    assert [item.value for item in CandidateStatus] == [
        "GENERATED",
        "VALIDATED",
        "NEED_REVIEW",
        "APPROVED",
        "REJECTED",
        "SAVED",
    ]
    assert [item.value for item in CandidateLabel] == [
        "GOOD",
        "NEED_REVIEW",
        "REJECTED",
    ]
    assert ParaphraseMode.STEM_ONLY.value == "STEM_ONLY"
    assert [item.value for item in Language] == ["vi", "en", "bilingual"]
    assert [item.value for item in GenerationProvider] == ["mock", "api", "local"]
