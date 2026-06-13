"""Deterministic local embedding for tests and offline demos."""

import hashlib
import re
import unicodedata

from app.modules.embeddings.interfaces import normalize_vector
from app.modules.normalization.text_normalizer import TextNormalizer


class MockDeterministicEmbeddingService:
    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    @staticmethod
    def _features(text: str) -> list[str]:
        normalized = TextNormalizer.normalize_for_comparison(text)
        normalized = normalized.removeprefix("query:").strip()
        folded = "".join(
            char
            for char in unicodedata.normalize("NFD", normalized)
            if unicodedata.category(char) != "Mn"
        )
        tokens = re.findall(r"[a-z0-9%/]+", folded)
        aliases = {
            "airway": "abc",
            "breathing": "abc",
            "circulation": "abc",
            "duong": "abc" if "tho" in tokens else "duong",
            "ho": "abc" if "hap" in tokens else "ho",
            "tuan": "abc" if "hoan" in tokens else "tuan",
            "cap": "acute" if "tinh" in tokens else "cap",
            "cuu": "acute" if "cap" in tokens else "cuu",
            "song": "survival",
            "con": "survival" if "song" in tokens else "con",
            "dam": "ensure" if "bao" in tokens else "dam",
            "bao": "ensure" if "dam" in tokens else "bao",
            "muc": "purpose" if "dich" in tokens or "tieu" in tokens else "muc",
            "dich": "purpose" if "muc" in tokens else "dich",
            "tieu": "purpose" if "muc" in tokens else "tieu",
        }
        features = [aliases.get(token, token) for token in tokens]
        features += [f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1)]
        return features

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for feature in self._features(text):
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return normalize_vector(vector)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

    def get_model_info(self) -> dict:
        return {
            "modelName": "mock-deterministic-384",
            "dimension": self.dimension,
            "provider": "mock_deterministic",
        }
