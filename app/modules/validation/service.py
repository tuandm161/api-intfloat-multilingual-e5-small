"""Candidate semantic, lexical, and explainable rule validation."""

from collections import Counter
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import CandidateLabel, CandidateStatus, ParaphraseJobStatus
from app.db.models.paraphrase import ParaphraseCandidate
from app.modules.audit.service import AuditService
from app.modules.embeddings.interfaces import cosine_similarity
from app.modules.embeddings.vector_index import get_embedding_service
from app.modules.normalization.text_builders import E5InputFormatter, QuestionTextBuilder
from app.modules.paraphrase.service import ParaphraseService, candidate_to_dict
from app.modules.questions.service import QuestionService
from app.modules.validation.lexical import calculate_lexical_difference
from app.modules.validation.rules import (
    CONTAINS_ANSWER_HINT,
    EMPTY_OR_TOO_SHORT,
    FORMAT_CHANGED_TO_TRUE_FALSE,
    SEMANTIC_DRIFT,
    SEMANTIC_UNCERTAIN,
    TOO_LITTLE_REWRITE,
    TOO_LONG,
    TOO_SIMILAR_TO_SOURCE,
    changed_to_true_false,
    contains_answer_hint,
    contains_option_content,
)


class ValidationService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.paraphrases = ParaphraseService(db)
        self.audit = AuditService(db)

    def _semantic_similarity(self, source: str, candidate: str) -> float:
        service = get_embedding_service(self.settings)
        source_vector, candidate_vector = service.embed_texts(
            [
                E5InputFormatter.format_for_e5(source),
                E5InputFormatter.format_for_e5(candidate),
            ]
        )
        raw = cosine_similarity(source_vector, candidate_vector)
        if self.settings.embedding_provider == "mock_deterministic":
            return min(0.99, 0.72 + max(raw, 0.0) * 0.35)
        return raw

    def validate_candidate(self, candidate_id: str, *, commit: bool = True) -> dict:
        candidate = self.paraphrases.get_candidate_or_fail(candidate_id)
        source = QuestionService(self.db).get_or_fail(candidate.source_question_id)
        original_state = candidate_to_dict(candidate, source)
        warnings: list[str] = []

        candidate_question = _candidate_question_like(source, candidate)
        source_full_text = QuestionTextBuilder.build_full_question_text(source)
        candidate_full_text = QuestionTextBuilder.build_full_question_text(
            candidate_question
        )

        if (
            len(candidate.candidate_stem.strip()) < 15
            or not candidate_question.option_a
            or not candidate_question.option_b
            or not candidate_question.option_c
            or not candidate_question.option_d
        ):
            candidate.label = CandidateLabel.REJECTED.value
            candidate.status = CandidateStatus.VALIDATED.value
            candidate.warnings = [EMPTY_OR_TOO_SHORT]
        else:
            semantic = self._semantic_similarity(source_full_text, candidate_full_text)
            lexical_difference = calculate_lexical_difference(
                source_full_text, candidate_full_text
            )
            stem_lexical_difference = calculate_lexical_difference(
                source.stem, candidate.candidate_stem
            )
            candidate.semantic_similarity_to_source = semantic
            candidate.lexical_difference_from_source = lexical_difference

            if semantic < self.settings.validation_semantic_review_min:
                label = CandidateLabel.REJECTED
                warnings.append(SEMANTIC_DRIFT)
            elif semantic < self.settings.validation_semantic_pass_min:
                label = CandidateLabel.NEED_REVIEW
                warnings.append(SEMANTIC_UNCERTAIN)
            else:
                label = CandidateLabel.GOOD

            lexical_similarity = 1 - lexical_difference
            if lexical_similarity >= self.settings.validation_lexical_too_similar_max:
                warnings.append(TOO_SIMILAR_TO_SOURCE)
                if label is CandidateLabel.GOOD:
                    label = CandidateLabel.NEED_REVIEW
            if (
                lexical_difference <= self.settings.validation_lexical_too_different_min
                or stem_lexical_difference
                <= self.settings.validation_lexical_too_different_min
            ):
                warnings.append(TOO_LITTLE_REWRITE)
                label = CandidateLabel.REJECTED

            correct_option = getattr(source, f"option_{source.correct_answer.lower()}")
            option_texts = (
                source.option_a,
                source.option_b,
                source.option_c,
                source.option_d,
            )
            if contains_answer_hint(
                candidate.candidate_stem, correct_option
            ) or contains_option_content(
                candidate.candidate_stem, source.stem, option_texts
            ):
                warnings.append(CONTAINS_ANSWER_HINT)
                if label is CandidateLabel.GOOD:
                    label = CandidateLabel.NEED_REVIEW
            if changed_to_true_false(candidate.candidate_stem):
                warnings.append(FORMAT_CHANGED_TO_TRUE_FALSE)
                if label is CandidateLabel.GOOD:
                    label = CandidateLabel.NEED_REVIEW
                elif label is CandidateLabel.NEED_REVIEW and semantic < self.settings.validation_semantic_pass_min:
                    label = CandidateLabel.REJECTED
            if len(candidate.candidate_stem) > len(source.stem) * 2.5:
                warnings.append(TOO_LONG)
                if label is CandidateLabel.GOOD:
                    label = CandidateLabel.NEED_REVIEW

            candidate.label = label.value
            candidate.status = (
                CandidateStatus.NEED_REVIEW.value
                if label is CandidateLabel.NEED_REVIEW
                else CandidateStatus.VALIDATED.value
            )
            candidate.warnings = list(dict.fromkeys(warnings))

        self.audit.log(
            "ParaphraseCandidate",
            candidate.id,
            "PARAPHRASE_CANDIDATE_VALIDATED",
            before=original_state,
            after=candidate_to_dict(candidate, source),
        )
        if commit:
            self.db.commit()
        return candidate_to_dict(candidate, source)

    def validate_job(self, job_id: str) -> dict:
        job = self.paraphrases.get_job_or_fail(job_id)
        job.status = ParaphraseJobStatus.VALIDATING.value
        candidates = list(
            self.db.scalars(
                select(ParaphraseCandidate).where(ParaphraseCandidate.job_id == job.id)
            )
        )
        results = [self.validate_candidate(item.id, commit=False) for item in candidates]
        summary = Counter(result["label"] for result in results)
        job.status = ParaphraseJobStatus.COMPLETED.value
        self.db.commit()
        return {
            "jobId": job.id,
            "validatedCount": len(results),
            "summary": {
                label.value: summary.get(label.value, 0) for label in CandidateLabel
            },
        }


def _candidate_question_like(source, candidate: ParaphraseCandidate):
    return SimpleNamespace(
        stem=candidate.candidate_stem,
        option_a=candidate.option_a or source.option_a,
        option_b=candidate.option_b or source.option_b,
        option_c=candidate.option_c or source.option_c,
        option_d=candidate.option_d or source.option_d,
        correct_answer=source.correct_answer,
    )
