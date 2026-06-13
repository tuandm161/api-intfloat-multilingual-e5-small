"""Deterministic text normalization and hashing."""

import hashlib
import re
import unicodedata


class TextNormalizer:
    @staticmethod
    def normalize_medical_terms(text: str) -> str:
        text = re.sub(
            r"Airway\s*[,\-]\s*Breathing\s*[,\-]\s*Circulation",
            "Airway - Breathing - Circulation",
            text,
            flags=re.IGNORECASE,
        )
        return text

    @classmethod
    def normalize_for_display(cls, text: str) -> str:
        text = unicodedata.normalize("NFC", text)
        text = cls.normalize_medical_terms(text)
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line).strip()

    @classmethod
    def normalize_for_comparison(cls, text: str) -> str:
        text = cls.normalize_for_display(text).lower()
        text = text.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"}))
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        text = re.sub(r"([,.;:!?])(?=\S)", r"\1 ", text)
        text = re.sub(r"\s*-\s*", " - ", text)
        return re.sub(r"\s+", " ", text).strip()


def hash_normalized_text(text: str) -> str:
    normalized = TextNormalizer.normalize_for_comparison(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
