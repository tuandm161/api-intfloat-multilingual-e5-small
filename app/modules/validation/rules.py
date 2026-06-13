"""Explainable validation warning rules."""

from app.modules.normalization.text_normalizer import TextNormalizer

SEMANTIC_DRIFT = "SEMANTIC_DRIFT"
SEMANTIC_UNCERTAIN = "SEMANTIC_UNCERTAIN"
TOO_SIMILAR_TO_SOURCE = "TOO_SIMILAR_TO_SOURCE"
TOO_LITTLE_REWRITE = "TOO_LITTLE_REWRITE"
POSSIBLE_DUPLICATE_WITH_EXISTING_QUESTION = "POSSIBLE_DUPLICATE_WITH_EXISTING_QUESTION"
STRONG_DUPLICATE_WITH_EXISTING_QUESTION = "STRONG_DUPLICATE_WITH_EXISTING_QUESTION"
CONTAINS_ANSWER_HINT = "CONTAINS_ANSWER_HINT"
FORMAT_CHANGED_TO_TRUE_FALSE = "FORMAT_CHANGED_TO_TRUE_FALSE"
EMPTY_OR_TOO_SHORT = "EMPTY_OR_TOO_SHORT"
TOO_LONG = "TOO_LONG"
VECTOR_INDEX_NOT_READY = "VECTOR_INDEX_NOT_READY"
EDITED_REVALIDATION_REQUIRED = "EDITED_REVALIDATION_REQUIRED"


def contains_answer_hint(candidate: str, correct_option: str) -> bool:
    candidate_normalized = TextNormalizer.normalize_for_comparison(candidate)
    option_normalized = TextNormalizer.normalize_for_comparison(correct_option).rstrip(".")
    return len(option_normalized) >= 20 and option_normalized in candidate_normalized


def changed_to_true_false(candidate: str) -> bool:
    normalized = TextNormalizer.normalize_for_comparison(candidate)
    return any(
        phrase in normalized
        for phrase in ("đúng hay sai", "phải không", "đúng không", "is it true", "true or false")
    )
