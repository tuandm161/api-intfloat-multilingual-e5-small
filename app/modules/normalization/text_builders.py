"""Stable text builders for questions, E5, and generation prompts."""

import json
from typing import Protocol

from app.modules.normalization.text_normalizer import TextNormalizer


class QuestionLike(Protocol):
    stem: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: str


class QuestionTextBuilder:
    @staticmethod
    def build_stem_text(question: QuestionLike) -> str:
        return TextNormalizer.normalize_for_display(question.stem)

    @classmethod
    def build_full_question_text(cls, question: QuestionLike) -> str:
        return "\n".join(
            [
                f"Câu hỏi: {cls.build_stem_text(question)}",
                f"A. {TextNormalizer.normalize_for_display(question.option_a)}",
                f"B. {TextNormalizer.normalize_for_display(question.option_b)}",
                f"C. {TextNormalizer.normalize_for_display(question.option_c)}",
                f"D. {TextNormalizer.normalize_for_display(question.option_d)}",
                f"Đáp án đúng: {question.correct_answer}",
            ]
        )

    @classmethod
    def build_duplicate_search_text(cls, question: QuestionLike) -> str:
        return cls.build_stem_text(question)


class E5InputFormatter:
    @staticmethod
    def format_for_e5(text: str) -> str:
        normalized = TextNormalizer.normalize_for_display(text)
        if normalized.lower().startswith("query:"):
            return f"query: {normalized[6:].strip()}"
        return f"query: {normalized}"


class ParaphrasePromptBuilder:
    @staticmethod
    def build_stem_only_prompt(
        question: QuestionLike,
        requested_count: int,
        target_language: str,
        change_strength: str,
    ) -> str:
        schema = json.dumps(
            {"candidates": [{"stem": "..."}]}, ensure_ascii=False, indent=2
        )
        return f"""You are helping create safe paraphrases for a medical/nursing multiple-choice question.
Rewrite ONLY the question stem.
Do not answer the question.
Do not change the correct meaning.
Do not add new medical facts.
Do not make the answer obvious.
Do not change the options.
Return exactly {requested_count} paraphrases.
Language: {target_language}
Change strength: {change_strength}

Original stem:
{question.stem}

Options for context only:
A. {question.option_a}
B. {question.option_b}
C. {question.option_c}
D. {question.option_d}
Correct answer: {question.correct_answer}

Return JSON only:
{schema}"""
