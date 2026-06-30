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


@dataclass
class GeneratedParaphrase:
    stem: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str


class ParaphraseGenerator(Protocol):
    def generate_paraphrases(self, request: GenerateRequest) -> list[GeneratedParaphrase]: ...
