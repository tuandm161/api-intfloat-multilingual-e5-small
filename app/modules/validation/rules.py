"""Explainable validation warning rules."""

import re

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

_OPTION_STOPWORDS = {
    "a",
    "b",
    "c",
    "d",
    "ai",
    "bi",
    "bị",
    "bo",
    "bỏ",
    "cac",
    "các",
    "cai",
    "cái",
    "cho",
    "co",
    "có",
    "cua",
    "của",
    "de",
    "để",
    "do",
    "đó",
    "duoc",
    "được",
    "hay",
    "hoac",
    "hoặc",
    "khi",
    "la",
    "là",
    "mot",
    "một",
    "nao",
    "nào",
    "neu",
    "nếu",
    "nguoi",
    "người",
    "nham",
    "nhằm",
    "o",
    "ở",
    "sau",
    "the",
    "thể",
    "thi",
    "thì",
    "trong",
    "va",
    "và",
    "ve",
    "về",
    "voi",
    "với",
    "vua",
    "vừa",
}


def contains_answer_hint(candidate: str, correct_option: str) -> bool:
    candidate_normalized = TextNormalizer.normalize_for_comparison(candidate)
    option_normalized = TextNormalizer.normalize_for_comparison(correct_option).rstrip(".")
    return len(option_normalized) >= 20 and option_normalized in candidate_normalized


def contains_option_content(
    candidate: str,
    source_stem: str,
    option_texts: list[str] | tuple[str, ...],
) -> bool:
    """Return true when a rewritten stem leaks answer-option-only content."""
    candidate_normalized = TextNormalizer.normalize_for_comparison(candidate)
    source_normalized = TextNormalizer.normalize_for_comparison(source_stem)
    for option_text in option_texts:
        option_normalized = TextNormalizer.normalize_for_comparison(option_text).rstrip(".")
        if not option_normalized or option_normalized in source_normalized:
            continue
        if any(
            term in candidate_normalized
            for term in _option_only_terms(option_text, source_stem)
        ):
            return True
        if len(option_normalized) >= 20 and option_normalized in candidate_normalized:
            return True
        if any(
            phrase in candidate_normalized
            for phrase in _option_only_phrases(option_normalized, source_normalized)
        ):
            return True
    return False


def changed_to_true_false(candidate: str) -> bool:
    normalized = TextNormalizer.normalize_for_comparison(candidate)
    return any(
        phrase in normalized
        for phrase in ("đúng hay sai", "phải không", "đúng không", "is it true", "true or false")
    )


def _option_only_phrases(option_normalized: str, source_normalized: str) -> set[str]:
    tokens = re.findall(r"\w+", option_normalized, flags=re.UNICODE)
    phrases: set[str] = set()
    for window_size in (3, 4):
        for index in range(0, max(len(tokens) - window_size + 1, 0)):
            window = tokens[index : index + window_size]
            phrase = " ".join(window)
            if phrase in source_normalized:
                continue
            content_tokens = [
                token
                for token in window
                if token not in _OPTION_STOPWORDS and (len(token) >= 3 or token.isdigit())
            ]
            if len(content_tokens) >= 2:
                phrases.add(phrase)
    return phrases


def _option_only_terms(option_text: str, source_stem: str) -> set[str]:
    source_normalized = TextNormalizer.normalize_for_comparison(source_stem)
    terms: set[str] = set()
    pattern = (
        r"\b(?:[A-Z]{2,}\d*|[A-Za-z]*[A-Z][a-z]*\d+[A-Za-z0-9]*|"
        r"mmHg|mmol/L|ml/kg/h|HbA1c|SpO2)\b"
        r"|(?:[<>]=?\s*)?\d+(?:[.,]\d+)?"
        r"(?:\s*(?:-|–|—)\s*\d+(?:[.,]\d+)?)?"
        r"(?:\s*(?:%|mmHg|mmol/L|ml/kg/h|lần/phút|phút|giờ|ngày))?"
    )
    for match in re.finditer(pattern, option_text):
        term = TextNormalizer.normalize_for_comparison(match.group(0).strip())
        if term and term not in source_normalized:
            terms.add(term)
    return terms
