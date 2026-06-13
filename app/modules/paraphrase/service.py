"""Paraphrase generation workflow."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    CandidateStatus,
    ErrorCode,
    GenerationProvider,
    ParaphraseJobStatus,
    QuestionStatus,
)
from app.core.errors import AppError
from app.db.models.paraphrase import ParaphraseCandidate, ParaphraseJob
from app.modules.audit.service import AuditService
from app.modules.normalization.text_normalizer import TextNormalizer
from app.modules.paraphrase.providers.api import ApiParaphraseGenerator
from app.modules.paraphrase.providers.base import GenerateRequest
from app.modules.paraphrase.providers.local import LocalParaphraseGenerator
from app.modules.paraphrase.providers.mock import MockParaphraseGenerator
from app.modules.paraphrase.schemas import ParaphraseJobCreate
from app.modules.questions.service import QuestionService, question_to_dict


def candidate_to_dict(candidate: ParaphraseCandidate) -> dict:
    return {
        "id": candidate.id,
        "jobId": candidate.job_id,
        "sourceQuestionId": candidate.source_question_id,
        "candidateStem": candidate.candidate_stem,
        "semanticSimilarityToSource": candidate.semantic_similarity_to_source,
        "lexicalDifferenceFromSource": candidate.lexical_difference_from_source,
        "duplicateMaxSimilarity": candidate.duplicate_max_similarity,
        "duplicateQuestionId": candidate.duplicate_question_id,
        "duplicateQuestionStemSnapshot": candidate.duplicate_question_stem_snapshot,
        "label": candidate.label,
        "warnings": candidate.warnings or [],
        "status": candidate.status,
        "reviewerNotes": candidate.reviewer_notes,
        "createdAt": candidate.created_at,
        "updatedAt": candidate.updated_at,
    }


class ParaphraseService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    def _provider(self, provider: GenerationProvider):
        return {
            GenerationProvider.mock: MockParaphraseGenerator,
            GenerationProvider.api: ApiParaphraseGenerator,
            GenerationProvider.local: LocalParaphraseGenerator,
        }[provider]()

    def get_job_or_fail(self, job_id: str) -> ParaphraseJob:
        job = self.db.get(ParaphraseJob, job_id)
        if not job:
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"Không tìm thấy phiên diễn đạt lại {job_id}",
                status_code=404,
            )
        return job

    def get_candidate_or_fail(self, candidate_id: str) -> ParaphraseCandidate:
        candidate = self.db.get(ParaphraseCandidate, candidate_id)
        if not candidate:
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"Không tìm thấy câu diễn đạt lại {candidate_id}",
                status_code=404,
            )
        return candidate

    def create_job(self, payload: ParaphraseJobCreate) -> dict:
        source = QuestionService(self.db).get_or_fail(payload.source_question_id)
        if source.status == QuestionStatus.ARCHIVED.value:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "Không thể diễn đạt lại câu hỏi đã lưu trữ",
            )
        job = ParaphraseJob(
            id=f"PJ-{uuid4().hex[:8].upper()}",
            source_question_id=source.id,
            mode=payload.mode.value,
            target_language=(payload.target_language.value if payload.target_language else source.language),
            requested_count=payload.requested_count,
            change_strength=payload.change_strength,
            provider=payload.provider.value,
            status=ParaphraseJobStatus.CREATED.value,
            created_by="demo-user",
        )
        self.db.add(job)
        self.audit.log("ParaphraseJob", job.id, "PARAPHRASE_JOB_CREATED", actor="demo-user")
        self.db.flush()
        try:
            job.status = ParaphraseJobStatus.GENERATING.value
            generated = self._provider(payload.provider).generate_stem_paraphrases(
                GenerateRequest(
                    source=source,
                    requested_count=payload.requested_count,
                    target_language=job.target_language,
                    change_strength=job.change_strength,
                )
            )
            source_normalized = TextNormalizer.normalize_for_comparison(source.stem)
            seen: set[str] = set()
            candidates = []
            for stem in generated:
                display = TextNormalizer.normalize_for_display(stem)
                normalized = TextNormalizer.normalize_for_comparison(display)
                if not display or normalized in seen or normalized == source_normalized:
                    continue
                seen.add(normalized)
                candidate = ParaphraseCandidate(
                    id=f"PC-{uuid4().hex[:8].upper()}",
                    job_id=job.id,
                    source_question_id=source.id,
                    candidate_stem=display,
                    normalized_candidate_stem=normalized,
                    warnings=[],
                    status=CandidateStatus.GENERATED.value,
                )
                self.db.add(candidate)
                candidates.append(candidate)
            job.status = ParaphraseJobStatus.GENERATED.value
            self.audit.log(
                "ParaphraseJob",
                job.id,
                "PARAPHRASE_CANDIDATES_GENERATED",
                after={"candidateCount": len(candidates)},
            )
            self.db.commit()
            return {"jobId": job.id, "status": job.status, "candidateCount": len(candidates)}
        except Exception as exc:
            job.status = ParaphraseJobStatus.FAILED.value
            job.error_message = str(exc)
            for candidate in list(job.candidates):
                self.db.delete(candidate)
            self.db.commit()
            if isinstance(exc, AppError):
                raise AppError(
                    exc.code,
                    exc.message,
                    status_code=exc.status_code,
                    details={"jobId": job.id, "reason": exc.details},
                ) from exc
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "Không thể tạo câu diễn đạt lại",
                status_code=503,
                details={"reason": str(exc), "jobId": job.id},
            ) from exc

    def retry_job(self, job_id: str) -> dict:
        job = self.get_job_or_fail(job_id)
        if job.status != ParaphraseJobStatus.FAILED.value:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "Chỉ có thể thử lại phiên đã thất bại",
            )
        return self.create_job(
            ParaphraseJobCreate(
                sourceQuestionId=job.source_question_id,
                mode=job.mode,
                requestedCount=job.requested_count,
                targetLanguage=job.target_language,
                changeStrength=job.change_strength,
                provider=job.provider,
            )
        )

    def list_jobs(self) -> list[dict]:
        jobs = list(
            self.db.scalars(
                select(ParaphraseJob).order_by(ParaphraseJob.created_at.desc())
            )
        )
        return [
            {
                "id": job.id,
                "sourceQuestionId": job.source_question_id,
                "provider": job.provider,
                "status": job.status,
                "requestedCount": job.requested_count,
                "createdAt": job.created_at,
            }
            for job in jobs
        ]

    def detail(self, job_id: str) -> dict:
        job = self.get_job_or_fail(job_id)
        source = QuestionService(self.db).get_or_fail(job.source_question_id)
        candidates = list(
            self.db.scalars(
                select(ParaphraseCandidate)
                .where(ParaphraseCandidate.job_id == job.id)
                .order_by(ParaphraseCandidate.created_at)
            )
        )
        return {
            "id": job.id,
            "sourceQuestion": question_to_dict(source),
            "status": job.status,
            "requestedCount": job.requested_count,
            "targetLanguage": job.target_language,
            "changeStrength": job.change_strength,
            "provider": job.provider,
            "errorMessage": job.error_message,
            "candidates": [candidate_to_dict(item) for item in candidates],
        }
