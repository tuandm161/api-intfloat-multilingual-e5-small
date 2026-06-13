"""Token-based lexical difference scoring."""

import re

from app.modules.normalization.text_normalizer import TextNormalizer


def tokenize(text: str) -> set[str]:
    normalized = TextNormalizer.normalize_for_comparison(text)
    return set(re.findall(r"\w+", normalized, flags=re.UNICODE))


def calculate_lexical_difference(source: str, candidate: str) -> float:
    source_tokens = tokenize(source)
    candidate_tokens = tokenize(candidate)
    if not source_tokens and not candidate_tokens:
        return 0.0
    union = source_tokens | candidate_tokens
    similarity = len(source_tokens & candidate_tokens) / len(union) if union else 1.0
    return 1.0 - similarity
