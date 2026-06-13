from types import SimpleNamespace

from app.modules.normalization.text_builders import (
    E5InputFormatter,
    ParaphrasePromptBuilder,
    QuestionTextBuilder,
)
from app.modules.normalization.text_normalizer import TextNormalizer, hash_normalized_text


def sample_question():
    return SimpleNamespace(
        stem="  Trong chăm sóc   cấp tính, ABC nhằm mục đích gì?  ",
        option_a="A one",
        option_b="B two",
        option_c="C three",
        option_d="D four",
        correct_answer="B",
    )


def test_normalization_preserves_vietnamese_and_medical_abbreviations() -> None:
    result = TextNormalizer.normalize_for_display(sample_question().stem)
    assert result == "Trong chăm sóc cấp tính, ABC nhằm mục đích gì?"


def test_medical_terms_and_comparison_normalization() -> None:
    assert TextNormalizer.normalize_medical_terms(
        "Airway-Breathing-Circulation"
    ) == "Airway - Breathing - Circulation"
    assert TextNormalizer.normalize_for_comparison("  ABC  Nhằm  Mục Đích Gì? ") == "abc nhằm mục đích gì?"


def test_e5_formatter_adds_prefix_exactly_once() -> None:
    assert E5InputFormatter.format_for_e5("ABC") == "query: ABC"
    assert E5InputFormatter.format_for_e5("query: ABC") == "query: ABC"


def test_question_and_prompt_builders_follow_contract() -> None:
    question = sample_question()
    full = QuestionTextBuilder.build_full_question_text(question)
    prompt = ParaphrasePromptBuilder.build_stem_only_prompt(question, 5, "vi", "medium")
    assert all(item in full for item in ("A. A one", "B. B two", "C. C three", "D. D four", "Đáp án đúng: B"))
    assert QuestionTextBuilder.build_duplicate_search_text(question) == QuestionTextBuilder.build_stem_text(question)
    assert "Rewrite ONLY" in prompt and "Return JSON only" in prompt and "Do not answer" in prompt


def test_hash_is_stable_for_equivalent_text() -> None:
    assert hash_normalized_text("  ABC Test ") == hash_normalized_text("abc   test")
