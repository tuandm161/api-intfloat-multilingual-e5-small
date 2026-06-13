"""Generator provider interface."""

from dataclasses import dataclass
from typing import Protocol

from app.db.models.question import Question


@dataclass
class GenerateRequest:
    source: Question
    requested_count: int
    target_language: str
    change_strength: str


class ParaphraseGenerator(Protocol):
    def generate_stem_paraphrases(self, request: GenerateRequest) -> list[str]: ...
