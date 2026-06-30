"""Document ingestion, chunking, generation, and review workflow."""

import hashlib
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import (
    CandidateLabel,
    CandidateStatus,
    ErrorCode,
    GenerationProvider,
    QuestionStatus,
    QuestionType,
)
from app.core.errors import AppError
from app.db.models.document import (
    Document,
    DocumentChunk,
    DocumentKnowledgePoint,
    DocumentSection,
    DocumentQuestionCandidate,
    DocumentQuestionJob,
)
from app.db.models.question import Question
from app.modules.audit.service import AuditService
from app.modules.documents.extractors import extract_pages
from app.modules.documents.processing import build_section_tree, clean_pages, split_into_chunks
from app.modules.documents.providers import (
    DeepSeekDocumentQuestionGenerator,
    DOCUMENT_GENERATION_PROMPT_VERSION,
    DocumentQuestionBatch,
    MockDocumentQuestionGenerator,
)
from app.modules.documents.schemas import DocumentQuestionCandidateEdit
from app.modules.embeddings.interfaces import cosine_similarity
from app.modules.embeddings.vector_index import embed_question, get_embedding_service, vector_index
from app.modules.normalization.text_builders import E5InputFormatter
from app.modules.normalization.text_normalizer import TextNormalizer
from app.modules.validation.lexical import tokenize
from app.modules.validation.rules import (
    POSSIBLE_DUPLICATE_WITH_EXISTING_QUESTION,
    STRONG_DUPLICATE_WITH_EXISTING_QUESTION,
    VECTOR_INDEX_NOT_READY,
)

DOCUMENT_SCHEMA_INVALID = "DOCUMENT_SCHEMA_INVALID"
SOURCE_EXCERPT_MISSING = "SOURCE_EXCERPT_MISSING"
SOURCE_EXCERPT_NOT_FOUND = "SOURCE_EXCERPT_NOT_FOUND"
DUPLICATE_WITH_DOCUMENT_CANDIDATE = "DUPLICATE_WITH_DOCUMENT_CANDIDATE"
DOCUMENT_OPTION_DUPLICATE = "DOCUMENT_OPTION_DUPLICATE"
DOCUMENT_OPTION_INVALID_PATTERN = "DOCUMENT_OPTION_INVALID_PATTERN"
DOCUMENT_LLM_NOT_ANSWERABLE = "DOCUMENT_LLM_NOT_ANSWERABLE"
DOCUMENT_LLM_MULTIPLE_ANSWERS = "DOCUMENT_LLM_MULTIPLE_ANSWERS"
DOCUMENT_LLM_CORRECT_ANSWER_UNSUPPORTED = "DOCUMENT_LLM_CORRECT_ANSWER_UNSUPPORTED"
DOCUMENT_LLM_LOW_QUALITY = "DOCUMENT_LLM_LOW_QUALITY"
DOCUMENT_LLM_VALIDATION_FAILED = "DOCUMENT_LLM_VALIDATION_FAILED"


def document_to_dict(document: Document, *, include_chunks: bool = False) -> dict:
    data = {
        "id": document.id,
        "filename": document.filename,
        "contentType": document.content_type,
        "status": document.status,
        "pageCount": document.page_count,
        "chunkCount": document.chunk_count,
        "errorMessage": document.error_message,
        "createdAt": document.created_at,
        "updatedAt": document.updated_at,
    }
    if include_chunks:
        data["sections"] = [section_to_dict(section) for section in document.sections]
        data["chunks"] = [chunk_to_dict(chunk) for chunk in document.chunks]
        data["questionJobs"] = [job_to_dict(job) for job in document.question_jobs]
    return data


def section_to_dict(section: DocumentSection) -> dict:
    return {
        "id": section.id,
        "documentId": section.document_id,
        "parentId": section.parent_id,
        "title": section.title,
        "level": section.level,
        "orderIndex": section.order_index,
        "pageStart": section.page_start,
        "pageEnd": section.page_end,
        "path": section.path,
        "confidence": section.confidence,
    }


def chunk_to_dict(chunk: DocumentChunk) -> dict:
    return {
        "id": chunk.id,
        "documentId": chunk.document_id,
        "sectionId": chunk.section_id,
        "parentChunkId": chunk.parent_chunk_id,
        "chunkIndex": chunk.chunk_index,
        "chunkType": chunk.chunk_type,
        "pageStart": chunk.page_start,
        "pageEnd": chunk.page_end,
        "sectionTitle": chunk.section_title,
        "sectionPath": chunk.section_path,
        "text": chunk.text,
        "textHash": chunk.text_hash,
        "charCount": chunk.char_count,
        "tokenCount": chunk.token_count,
        "qualityFlags": chunk.quality_flags or [],
        "previousChunkId": chunk.previous_chunk_id,
        "nextChunkId": chunk.next_chunk_id,
    }


def job_to_dict(job: DocumentQuestionJob, *, include_candidates: bool = False) -> dict:
    data = {
        "id": job.id,
        "documentId": job.document_id,
        "provider": job.provider,
        "model": job.model,
        "promptVersion": job.prompt_version,
        "status": job.status,
        "questionsPerChunk": job.questions_per_chunk,
        "chunkCount": job.chunk_count,
        "completedChunkCount": job.completed_chunk_count,
        "failedChunkCount": job.failed_chunk_count,
        "chunkErrors": job.chunk_errors or [],
        "candidateCount": job.candidate_count,
        "llmCallCount": job.llm_call_count,
        "totalPromptTokens": job.total_prompt_tokens,
        "totalCompletionTokens": job.total_completion_tokens,
        "totalTokens": job.total_tokens,
        "totalLatencyMs": job.total_latency_ms,
        "estimatedCostUsd": job.estimated_cost_usd,
        "errorMessage": job.error_message,
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
    }
    if include_candidates:
        data["knowledgePoints"] = [
            knowledge_point_to_dict(item) for item in job.knowledge_points
        ]
        data["candidates"] = [candidate_to_dict(candidate) for candidate in job.candidates]
    return data


def knowledge_point_to_dict(item: DocumentKnowledgePoint) -> dict:
    return {
        "id": item.id,
        "jobId": item.job_id,
        "documentId": item.document_id,
        "chunkId": item.chunk_id,
        "sourceKey": item.source_key,
        "statement": item.statement,
        "knowledgeType": item.knowledge_type,
        "importance": item.importance,
        "sourceExcerpt": item.source_excerpt,
        "generationEligible": item.generation_eligible,
        "rawJson": item.raw_json or {},
        "createdAt": item.created_at,
    }


def candidate_to_dict(candidate: DocumentQuestionCandidate) -> dict:
    return {
        "id": candidate.id,
        "jobId": candidate.job_id,
        "documentId": candidate.document_id,
        "chunkId": candidate.chunk_id,
        "stem": candidate.stem,
        "options": {
            "A": candidate.option_a,
            "B": candidate.option_b,
            "C": candidate.option_c,
            "D": candidate.option_d,
        },
        "correctAnswer": candidate.correct_answer,
        "explanation": candidate.explanation,
        "topic": candidate.topic,
        "difficulty": candidate.difficulty,
        "sourceExcerpt": candidate.source_excerpt,
        "sourcePageStart": candidate.chunk.page_start if candidate.chunk else None,
        "sourcePageEnd": candidate.chunk.page_end if candidate.chunk else None,
        "sourceSectionTitle": candidate.chunk.section_title if candidate.chunk else None,
        "sourceSectionPath": candidate.chunk.section_path if candidate.chunk else None,
        "generationKey": candidate.generation_key,
        "qualityScore": candidate.quality_score,
        "llmValidation": candidate.llm_validation,
        "label": candidate.label,
        "warnings": candidate.warnings or [],
        "status": candidate.status,
        "duplicateMaxSimilarity": candidate.duplicate_max_similarity,
        "duplicateQuestionId": candidate.duplicate_question_id,
        "duplicateQuestionStemSnapshot": candidate.duplicate_question_stem_snapshot,
        "reviewerNotes": candidate.reviewer_notes,
        "savedQuestionId": candidate.saved_question_id,
        "createdAt": candidate.created_at,
        "updatedAt": candidate.updated_at,
    }


class DocumentService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.audit = AuditService(db)

    def list_documents(self) -> list[dict]:
        documents = list(self.db.scalars(select(Document).order_by(Document.created_at.desc())))
        return [document_to_dict(document) for document in documents]

    def get_or_fail(self, document_id: str) -> Document:
        document = self.db.get(Document, document_id)
        if not document:
            raise AppError(ErrorCode.NOT_FOUND, f"Không tìm thấy tài liệu {document_id}", status_code=404)
        return document

    def get_job_or_fail(self, job_id: str) -> DocumentQuestionJob:
        job = self.db.get(DocumentQuestionJob, job_id)
        if not job:
            raise AppError(ErrorCode.NOT_FOUND, f"Không tìm thấy phiên tạo câu hỏi {job_id}", status_code=404)
        return job

    def get_candidate_or_fail(self, candidate_id: str) -> DocumentQuestionCandidate:
        candidate = self.db.get(DocumentQuestionCandidate, candidate_id)
        if not candidate:
            raise AppError(ErrorCode.NOT_FOUND, f"Không tìm thấy câu hỏi đề xuất {candidate_id}", status_code=404)
        return candidate

    def detail(self, document_id: str) -> dict:
        return document_to_dict(self.get_or_fail(document_id), include_chunks=True)

    def upload_document(self, *, filename: str, content_type: str | None, content: bytes) -> dict:
        pages = extract_pages(filename, content)
        cleaned_pages = clean_pages(pages)
        section_drafts = build_section_tree(cleaned_pages)
        chunks = split_into_chunks(
            cleaned_pages,
            target_chars=self.settings.document_chunk_target_chars,
            max_chars=self.settings.document_chunk_max_chars,
            overlap_chars=self.settings.document_chunk_overlap_chars,
        )
        document = Document(
            id=f"DOC-{uuid4().hex[:8].upper()}",
            filename=filename,
            content_type=content_type,
            status="READY" if chunks else "OCR_REQUIRED",
            page_count=len(pages),
            chunk_count=len(chunks),
            error_message=None if chunks else "Không trích xuất được đủ text. Tài liệu có thể là bản scan và cần OCR.",
            created_by="demo-user",
        )
        self.db.add(document)
        self.db.flush()
        section_id_by_index: dict[int, str] = {}
        section_id_by_title: dict[str, str] = {}
        section_path_by_title: dict[str, str] = {}
        for section in section_drafts:
            section_id = f"SEC-{uuid4().hex[:8].upper()}"
            section_id_by_index[section.section_index] = section_id
            section_id_by_title[section.title] = section_id
            section_path_by_title[section.title] = section.path
            self.db.add(
                DocumentSection(
                    id=section_id,
                    document_id=document.id,
                    parent_id=(
                        section_id_by_index.get(section.parent_index)
                        if section.parent_index is not None
                        else None
                    ),
                    title=section.title,
                    level=section.level,
                    order_index=section.section_index,
                    page_start=section.page_start,
                    page_end=section.page_end,
                    path=section.path,
                    confidence=section.confidence,
                )
            )
        previous_chunk: DocumentChunk | None = None
        for chunk in chunks:
            chunk_model = DocumentChunk(
                id=f"CH-{uuid4().hex[:8].upper()}",
                document_id=document.id,
                section_id=section_id_by_title.get(chunk.section_title or ""),
                parent_chunk_id=None,
                chunk_index=chunk.chunk_index,
                chunk_type="generation",
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_title=chunk.section_title,
                section_path=chunk.section_path or section_path_by_title.get(chunk.section_title or ""),
                text=chunk.text,
                text_hash=chunk.text_hash,
                char_count=len(chunk.text),
                token_count=chunk.token_count,
                quality_flags=chunk.quality_flags,
                previous_chunk_id=previous_chunk.id if previous_chunk else None,
            )
            if previous_chunk:
                previous_chunk.next_chunk_id = chunk_model.id
            self.db.add(chunk_model)
            previous_chunk = chunk_model
        self.audit.log(
            "Document",
            document.id,
            "DOCUMENT_UPLOADED",
            actor="demo-user",
            after={"filename": document.filename, "status": document.status, "chunkCount": document.chunk_count},
        )
        self.db.commit()
        return document_to_dict(document, include_chunks=True)

    def create_question_job(self, document_id: str, questions_per_chunk: int | None = None) -> dict:
        document = self.get_or_fail(document_id)
        if document.status != "READY" or not document.chunks:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "Tài liệu chưa sẵn sàng để tạo câu hỏi",
                details={"status": document.status},
            )
        count = questions_per_chunk or self.settings.document_questions_per_chunk
        job = DocumentQuestionJob(
            id=f"DQJ-{uuid4().hex[:8].upper()}",
            document_id=document.id,
            provider=self.settings.generation_provider.value,
            model=(
                self.settings.generation_model
                if self.settings.generation_provider is GenerationProvider.api
                else "mock-document-generator"
            ),
            prompt_version=None,
            status="CREATED",
            questions_per_chunk=count,
            chunk_count=len(document.chunks),
            created_by="demo-user",
        )
        self.db.add(job)
        self.audit.log("DocumentQuestionJob", job.id, "DOCUMENT_QUESTION_JOB_CREATED", actor="demo-user")
        self.db.flush()
        try:
            job.status = "GENERATING"
            generator = self._question_generator()
            previous: list[dict[str, Any]] = []
            chunk_errors: list[dict[str, Any]] = []
            for chunk in document.chunks:
                try:
                    created = self._generate_chunk_candidates(
                        generator=generator,
                        job=job,
                        chunk=chunk,
                        questions_per_chunk=count,
                        previous=previous,
                    )
                    job.completed_chunk_count = (job.completed_chunk_count or 0) + 1
                    if created == 0:
                        chunk_errors.append(
                            self._chunk_error(chunk, "NO_QUESTIONS", "Không sinh được câu hỏi phù hợp")
                        )
                        job.failed_chunk_count = (job.failed_chunk_count or 0) + 1
                except Exception as exc:
                    chunk_errors.append(self._chunk_error(chunk, type(exc).__name__, str(exc)))
                    job.failed_chunk_count = (job.failed_chunk_count or 0) + 1
                    continue
                finally:
                    job.chunk_errors = chunk_errors
                    self.db.flush()
            job.candidate_count = self._job_candidate_count(job.id)
            if job.candidate_count == 0 and chunk_errors:
                raise AppError(
                    ErrorCode.GENERATION_FAILED,
                    "Không thể tạo câu hỏi từ bất kỳ chunk nào",
                    status_code=503,
                    details={"chunkErrors": chunk_errors},
                )
            job.status = "GENERATED" if not chunk_errors else "PARTIALLY_COMPLETED"
            self.audit.log(
                "DocumentQuestionJob",
                job.id,
                "DOCUMENT_QUESTION_CANDIDATES_GENERATED",
                actor="demo-user",
                after={
                    "candidateCount": job.candidate_count,
                    "completedChunkCount": job.completed_chunk_count,
                    "failedChunkCount": job.failed_chunk_count,
                },
            )
            self.db.commit()
            return job_to_dict(job, include_candidates=True)
        except Exception as exc:
            job.status = "FAILED"
            job.error_message = str(exc)
            self.db.commit()
            if isinstance(exc, AppError):
                raise AppError(
                    exc.code,
                    exc.message,
                    status_code=exc.status_code,
                    details={"jobId": job.id, "reason": exc.details or exc.message},
                ) from exc
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "Không thể tạo câu hỏi từ tài liệu",
                status_code=503,
                details={"jobId": job.id, "reason": str(exc)},
            ) from exc

    def _question_generator(self):
        if self.settings.generation_provider is GenerationProvider.api:
            return DeepSeekDocumentQuestionGenerator(self.settings)
        return MockDocumentQuestionGenerator(self.settings)

    def retry_failed_job_chunks(self, job_id: str) -> dict:
        job = self.get_job_or_fail(job_id)
        if job.status not in {"FAILED", "PARTIALLY_COMPLETED"}:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "Chỉ có thể retry phiên tạo câu hỏi đang lỗi hoặc hoàn thành một phần",
                details={"status": job.status},
            )
        failed_chunk_ids = {
            item.get("chunkId") for item in (job.chunk_errors or []) if item.get("chunkId")
        }
        if not failed_chunk_ids:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "Phiên tạo câu hỏi không có chunk lỗi để retry",
            )
        generator = self._question_generator()
        previous = self._previous_job_candidates(job)
        remaining_errors: list[dict[str, Any]] = []
        job.status = "GENERATING"
        for chunk in job.document.chunks:
            if chunk.id not in failed_chunk_ids:
                continue
            try:
                created = self._generate_chunk_candidates(
                    generator=generator,
                    job=job,
                    chunk=chunk,
                    questions_per_chunk=job.questions_per_chunk,
                    previous=previous,
                )
                if created == 0:
                    remaining_errors.append(
                        self._chunk_error(chunk, "NO_QUESTIONS", "Không sinh được câu hỏi phù hợp")
                    )
            except Exception as exc:
                remaining_errors.append(self._chunk_error(chunk, type(exc).__name__, str(exc)))
        job.chunk_errors = remaining_errors
        job.failed_chunk_count = len(remaining_errors)
        job.completed_chunk_count = max(0, job.chunk_count - job.failed_chunk_count)
        job.candidate_count = self._job_candidate_count(job.id)
        job.status = "GENERATED" if not remaining_errors else "PARTIALLY_COMPLETED"
        self.audit.log(
            "DocumentQuestionJob",
            job.id,
            "DOCUMENT_QUESTION_JOB_RETRIED",
            actor="demo-user",
            after={
                "candidateCount": job.candidate_count,
                "failedChunkCount": job.failed_chunk_count,
            },
        )
        self.db.commit()
        return job_to_dict(job, include_candidates=True)

    def _generate_chunk_candidates(
        self,
        *,
        generator: Any,
        job: DocumentQuestionJob,
        chunk: DocumentChunk,
        questions_per_chunk: int,
        previous: list[dict[str, Any]],
    ) -> int:
        generation_key = self._generation_key(job, chunk, questions_per_chunk)
        cached = self._reuse_cached_chunk_candidates(
            job=job,
            chunk=chunk,
            generation_key=generation_key,
            questions_per_chunk=questions_per_chunk,
            previous=previous,
        )
        if cached >= questions_per_chunk:
            return cached
        raw_result = generator.generate_questions(
            chunk_text=chunk.text,
            questions_per_chunk=questions_per_chunk,
            target_language="vi",
        )
        batch = self._normalize_question_batch(raw_result, job.model)
        self._apply_generation_usage(job, batch)
        self._persist_knowledge_points(job, chunk, batch.knowledge_points)
        created = 0
        for raw in batch.questions:
            candidate = self._candidate_from_raw(job, chunk, raw, generation_key=generation_key)
            self.db.add(candidate)
            self.db.flush()
            self._validate_candidate(candidate, chunk, previous)
            self._llm_validate_candidate(candidate, chunk, generator, job)
            previous.append(
                {
                    "id": candidate.id,
                    "stem": candidate.stem,
                    "vector": self._embed_for_duplicate(candidate.stem) if candidate.stem else None,
                }
            )
            created += 1
        return created

    def _llm_validate_candidate(
        self,
        candidate: DocumentQuestionCandidate,
        chunk: DocumentChunk,
        generator: Any,
        job: DocumentQuestionJob,
    ) -> None:
        if candidate.label == CandidateLabel.REJECTED.value:
            return
        validate_question = getattr(generator, "validate_question", None)
        if not callable(validate_question):
            return
        try:
            validation = validate_question(
                chunk_text=chunk.text,
                question=self._candidate_validation_payload(candidate),
                target_language="vi",
            )
            self._apply_generation_usage(job, validation)
            result = validation.result if isinstance(validation.result, dict) else {}
            candidate.llm_validation = result
            candidate.quality_score = _coerce_quality_score(result.get("qualityScore"))
            self._apply_llm_validation_result(candidate, result)
        except Exception as exc:
            candidate.llm_validation = {"error": str(exc)[:500]}
            candidate.warnings = list(
                dict.fromkeys([*(candidate.warnings or []), DOCUMENT_LLM_VALIDATION_FAILED])
            )
            if candidate.label != CandidateLabel.REJECTED.value:
                candidate.label = CandidateLabel.NEED_REVIEW.value
                candidate.status = CandidateStatus.NEED_REVIEW.value

    @staticmethod
    def _candidate_validation_payload(candidate: DocumentQuestionCandidate) -> dict[str, Any]:
        return {
            "stem": candidate.stem,
            "optionA": candidate.option_a,
            "optionB": candidate.option_b,
            "optionC": candidate.option_c,
            "optionD": candidate.option_d,
            "correctAnswer": candidate.correct_answer,
            "explanation": candidate.explanation,
            "sourceExcerpt": candidate.source_excerpt,
        }

    def _apply_llm_validation_result(
        self, candidate: DocumentQuestionCandidate, result: dict[str, Any]
    ) -> None:
        warnings = list(candidate.warnings or [])
        severe = False
        if result.get("answerable") is False:
            warnings.append(DOCUMENT_LLM_NOT_ANSWERABLE)
            severe = True
        if result.get("singleBestAnswer") is False:
            warnings.append(DOCUMENT_LLM_MULTIPLE_ANSWERS)
            severe = True
        if result.get("correctAnswerSupported") is False:
            warnings.append(DOCUMENT_LLM_CORRECT_ANSWER_UNSUPPORTED)
            severe = True
        if candidate.quality_score is not None and candidate.quality_score < 0.55:
            warnings.append(DOCUMENT_LLM_LOW_QUALITY)
            severe = True
        candidate.warnings = list(dict.fromkeys(warnings))
        if severe:
            candidate.label = CandidateLabel.REJECTED.value
            candidate.status = CandidateStatus.VALIDATED.value
        elif warnings and candidate.label == CandidateLabel.GOOD.value:
            candidate.label = CandidateLabel.NEED_REVIEW.value
            candidate.status = CandidateStatus.NEED_REVIEW.value

    def _reuse_cached_chunk_candidates(
        self,
        *,
        job: DocumentQuestionJob,
        chunk: DocumentChunk,
        generation_key: str,
        questions_per_chunk: int,
        previous: list[dict[str, Any]],
    ) -> int:
        cached_items = list(
            self.db.scalars(
                select(DocumentQuestionCandidate)
                .where(
                    DocumentQuestionCandidate.chunk_id == chunk.id,
                    DocumentQuestionCandidate.generation_key == generation_key,
                    DocumentQuestionCandidate.job_id != job.id,
                )
                .order_by(DocumentQuestionCandidate.created_at)
            )
        )
        if len(cached_items) < questions_per_chunk:
            return 0
        created = 0
        for cached in cached_items[:questions_per_chunk]:
            raw = dict(cached.raw_json or {})
            raw["_cachedFromCandidateId"] = cached.id
            raw["_cachedFromJobId"] = cached.job_id
            candidate = self._candidate_from_raw(
                job,
                chunk,
                raw,
                generation_key=generation_key,
            )
            self.db.add(candidate)
            self.db.flush()
            self._validate_candidate(candidate, chunk, previous)
            previous.append(
                {
                    "id": candidate.id,
                    "stem": candidate.stem,
                    "vector": self._embed_for_duplicate(candidate.stem) if candidate.stem else None,
                }
            )
            created += 1
        job.prompt_version = job.prompt_version or self._expected_prompt_version(job)
        return created

    def _persist_knowledge_points(
        self,
        job: DocumentQuestionJob,
        chunk: DocumentChunk,
        knowledge_points: list[dict[str, Any]],
    ) -> None:
        for index, raw in enumerate(knowledge_points, start=1):
            if not isinstance(raw, dict):
                continue
            statement = TextNormalizer.normalize_for_display(str(raw.get("statement") or ""))
            if not statement:
                continue
            self.db.add(
                DocumentKnowledgePoint(
                    id=f"KP-{uuid4().hex[:8].upper()}",
                    job_id=job.id,
                    document_id=job.document_id,
                    chunk_id=chunk.id,
                    source_key=TextNormalizer.normalize_for_display(
                        str(raw.get("id") or f"KP{index}")
                    )[:64],
                    statement=statement,
                    knowledge_type=TextNormalizer.normalize_for_display(
                        str(raw.get("type") or raw.get("knowledgeType") or "")
                    )
                    or None,
                    importance=TextNormalizer.normalize_for_display(
                        str(raw.get("importance") or "")
                    )
                    or None,
                    source_excerpt=TextNormalizer.normalize_for_display(
                        str(raw.get("sourceExcerpt") or "")
                    )
                    or None,
                    generation_eligible=bool(raw.get("generationEligible", True)),
                    raw_json=raw,
                )
            )

    def _generation_key(
        self,
        job: DocumentQuestionJob,
        chunk: DocumentChunk,
        questions_per_chunk: int,
    ) -> str:
        payload = {
            "provider": job.provider,
            "model": job.model,
            "promptVersion": self._expected_prompt_version(job),
            "questionsPerChunk": questions_per_chunk,
            "chunkHash": chunk.text_hash,
            "targetLanguage": "vi",
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _expected_prompt_version(job: DocumentQuestionJob) -> str:
        if job.provider == GenerationProvider.api.value:
            return DOCUMENT_GENERATION_PROMPT_VERSION
        return "mock-document-generator-v1"

    @staticmethod
    def _chunk_error(chunk: DocumentChunk, code: str, message: str) -> dict[str, Any]:
        return {
            "chunkId": chunk.id,
            "chunkIndex": chunk.chunk_index,
            "pageStart": chunk.page_start,
            "pageEnd": chunk.page_end,
            "code": code,
            "message": message[:500],
        }

    def _previous_job_candidates(self, job: DocumentQuestionJob) -> list[dict[str, Any]]:
        return [
            {"id": item.id, "stem": item.stem, "vector": self._embed_for_duplicate(item.stem)}
            for item in job.candidates
            if item.stem
        ]

    def _job_candidate_count(self, job_id: str) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(DocumentQuestionCandidate).where(
                    DocumentQuestionCandidate.job_id == job_id
                )
            )
            or 0
        )

    @staticmethod
    def _normalize_question_batch(raw_result: Any, fallback_model: str | None) -> DocumentQuestionBatch:
        if isinstance(raw_result, DocumentQuestionBatch):
            return raw_result
        if isinstance(raw_result, list):
            from app.modules.documents.providers import DocumentGenerationUsage

            return DocumentQuestionBatch(
                questions=[item for item in raw_result if isinstance(item, dict)],
                model=fallback_model or "unknown",
                usage=DocumentGenerationUsage(),
                knowledge_points=[],
            )
        raise AppError(
            ErrorCode.GENERATION_FAILED,
            "Document generator returned an unsupported result",
            status_code=503,
            details={"type": type(raw_result).__name__},
        )

    def _apply_generation_usage(self, job: DocumentQuestionJob, batch: DocumentQuestionBatch) -> None:
        job.model = batch.model or job.model
        job.prompt_version = batch.prompt_version or job.prompt_version
        job.llm_call_count = (job.llm_call_count or 0) + batch.usage.call_count
        job.total_prompt_tokens = (job.total_prompt_tokens or 0) + batch.usage.prompt_tokens
        job.total_completion_tokens = (
            (job.total_completion_tokens or 0) + batch.usage.completion_tokens
        )
        job.total_tokens = (job.total_tokens or 0) + batch.usage.total_tokens
        job.total_latency_ms = (job.total_latency_ms or 0) + batch.usage.latency_ms
        job.estimated_cost_usd = round(
            (job.estimated_cost_usd or 0.0)
            + (
                batch.usage.prompt_tokens
                * self.settings.generation_prompt_usd_per_1m_tokens
                / 1_000_000
            )
            + (
                batch.usage.completion_tokens
                * self.settings.generation_completion_usd_per_1m_tokens
                / 1_000_000
            ),
            8,
        )

    def edit_candidate(self, candidate_id: str, payload: DocumentQuestionCandidateEdit) -> dict:
        candidate = self.get_candidate_or_fail(candidate_id)
        if candidate.status == CandidateStatus.SAVED.value:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Không thể chỉnh sửa câu đã lưu")
        before = candidate_to_dict(candidate)
        data = payload.model_dump(by_alias=False)
        for name, value in data.items():
            setattr(candidate, name, TextNormalizer.normalize_for_display(value) if isinstance(value, str) else value)
        candidate.correct_answer = candidate.correct_answer.upper()
        candidate.status = CandidateStatus.GENERATED.value
        candidate.label = None
        candidate.warnings = []
        candidate.duplicate_max_similarity = None
        candidate.duplicate_question_id = None
        candidate.duplicate_question_stem_snapshot = None
        candidate.quality_score = None
        candidate.llm_validation = None
        self._validate_candidate(candidate, candidate.chunk, self._previous_candidates(candidate))
        self.audit.log(
            "DocumentQuestionCandidate",
            candidate.id,
            "DOCUMENT_QUESTION_CANDIDATE_EDITED",
            actor="demo-user",
            before=before,
            after=candidate_to_dict(candidate),
        )
        self.db.commit()
        return candidate_to_dict(candidate)

    def approve_candidate(self, candidate_id: str, reviewer_notes: str | None) -> dict:
        candidate = self.get_candidate_or_fail(candidate_id)
        if candidate.status not in {CandidateStatus.VALIDATED.value, CandidateStatus.NEED_REVIEW.value} or not candidate.label:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Câu hỏi đề xuất phải được kiểm định trước khi duyệt")
        before = candidate_to_dict(candidate)
        candidate.status = CandidateStatus.APPROVED.value
        candidate.reviewer_notes = reviewer_notes
        self.audit.log(
            "DocumentQuestionCandidate",
            candidate.id,
            "DOCUMENT_QUESTION_CANDIDATE_APPROVED",
            actor="demo-user",
            before=before,
            after=candidate_to_dict(candidate),
        )
        self.db.commit()
        return {"candidateId": candidate.id, "status": candidate.status}

    def reject_candidate(self, candidate_id: str, reviewer_notes: str | None) -> dict:
        candidate = self.get_candidate_or_fail(candidate_id)
        if candidate.status == CandidateStatus.SAVED.value:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Không thể từ chối câu đã lưu")
        before = candidate_to_dict(candidate)
        candidate.status = CandidateStatus.REJECTED.value
        candidate.reviewer_notes = reviewer_notes
        self.audit.log(
            "DocumentQuestionCandidate",
            candidate.id,
            "DOCUMENT_QUESTION_CANDIDATE_REJECTED",
            actor="demo-user",
            before=before,
            after=candidate_to_dict(candidate),
        )
        self.db.commit()
        return {"candidateId": candidate.id, "status": candidate.status}

    def save_candidate_as_question(self, candidate_id: str) -> dict:
        candidate = self.get_candidate_or_fail(candidate_id)
        if candidate.status != CandidateStatus.APPROVED.value:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Chỉ có thể lưu câu hỏi đề xuất đã được duyệt")
        chunk = candidate.chunk
        document = self.get_or_fail(candidate.document_id)
        question = Question(
            id=f"QD-{uuid4().hex[:8].upper()}",
            stem=candidate.stem,
            option_a=candidate.option_a,
            option_b=candidate.option_b,
            option_c=candidate.option_c,
            option_d=candidate.option_d,
            correct_answer=candidate.correct_answer,
            explanation=candidate.explanation,
            topic=candidate.topic,
            difficulty=candidate.difficulty,
            language="vi",
            source_document=(
                f"{document.filename} ({document.id}, chunk {chunk.chunk_index}, "
                f"trang {chunk.page_start or '-'}-{chunk.page_end or '-'})"
            ),
            question_type=QuestionType.ORIGINAL.value,
            status=QuestionStatus.APPROVED.value,
            created_by="demo-user",
            reviewed_by="demo-user",
        )
        self.db.add(question)
        self.db.flush()
        embed_question(self.db, question, self.settings)
        before = candidate_to_dict(candidate)
        candidate.status = CandidateStatus.SAVED.value
        candidate.saved_question_id = question.id
        self.audit.log(
            "Question",
            question.id,
            "DOCUMENT_QUESTION_SAVED",
            actor="demo-user",
            after={"documentId": document.id, "chunkId": chunk.id, "candidateId": candidate.id},
        )
        self.audit.log(
            "DocumentQuestionCandidate",
            candidate.id,
            "DOCUMENT_QUESTION_CANDIDATE_SAVED",
            actor="demo-user",
            before=before,
            after=candidate_to_dict(candidate),
        )
        self.db.commit()
        return {"candidateId": candidate.id, "newQuestionId": question.id, "status": candidate.status}

    def _candidate_from_raw(
        self,
        job: DocumentQuestionJob,
        chunk: DocumentChunk,
        raw: dict[str, Any],
        *,
        generation_key: str | None = None,
    ) -> DocumentQuestionCandidate:
        return DocumentQuestionCandidate(
            id=f"DQC-{uuid4().hex[:8].upper()}",
            job_id=job.id,
            document_id=job.document_id,
            chunk_id=chunk.id,
            stem=TextNormalizer.normalize_for_display(str(raw.get("stem") or "")),
            option_a=TextNormalizer.normalize_for_display(str(raw.get("optionA") or "")),
            option_b=TextNormalizer.normalize_for_display(str(raw.get("optionB") or "")),
            option_c=TextNormalizer.normalize_for_display(str(raw.get("optionC") or "")),
            option_d=TextNormalizer.normalize_for_display(str(raw.get("optionD") or "")),
            correct_answer=str(raw.get("correctAnswer") or "").upper()[:1],
            explanation=TextNormalizer.normalize_for_display(str(raw.get("explanation") or "")) or None,
            topic=TextNormalizer.normalize_for_display(str(raw.get("topic") or "")) or None,
            difficulty=TextNormalizer.normalize_for_display(str(raw.get("difficulty") or "medium")) or "medium",
            source_excerpt=TextNormalizer.normalize_for_display(str(raw.get("sourceExcerpt") or "")) or None,
            generation_key=generation_key,
            raw_json=raw,
        )

    def _validate_candidate(
        self,
        candidate: DocumentQuestionCandidate,
        chunk: DocumentChunk,
        previous_candidates: list[dict[str, Any]],
    ) -> None:
        warnings: list[str] = []
        fatal = False
        if not all(
            [
                candidate.stem,
                candidate.option_a,
                candidate.option_b,
                candidate.option_c,
                candidate.option_d,
                candidate.correct_answer in {"A", "B", "C", "D"},
            ]
        ):
            warnings.append(DOCUMENT_SCHEMA_INVALID)
            fatal = True

        if not fatal:
            option_values = [
                candidate.option_a,
                candidate.option_b,
                candidate.option_c,
                candidate.option_d,
            ]
            normalized_options = [
                TextNormalizer.normalize_for_comparison(value) for value in option_values
            ]
            if len(set(normalized_options)) < 4:
                warnings.append(DOCUMENT_OPTION_DUPLICATE)
                fatal = True
            if any(_has_invalid_option_pattern(value) for value in option_values):
                warnings.append(DOCUMENT_OPTION_INVALID_PATTERN)
                fatal = True

        if not candidate.source_excerpt:
            warnings.append(SOURCE_EXCERPT_MISSING)
        elif not self._excerpt_matches_chunk(candidate.source_excerpt, chunk.text):
            warnings.append(SOURCE_EXCERPT_NOT_FOUND)

        normalized = TextNormalizer.normalize_for_comparison(candidate.stem)
        for previous in previous_candidates:
            if TextNormalizer.normalize_for_comparison(previous["stem"]) == normalized:
                warnings.append(DUPLICATE_WITH_DOCUMENT_CANDIDATE)
                candidate.duplicate_max_similarity = 1.0
                candidate.duplicate_question_id = previous["id"]
                candidate.duplicate_question_stem_snapshot = previous["stem"]
                fatal = True
                break

        if not fatal:
            duplicate = self._exact_bank_duplicate(normalized)
            if duplicate:
                warnings.append(STRONG_DUPLICATE_WITH_EXISTING_QUESTION)
                candidate.duplicate_max_similarity = 1.0
                candidate.duplicate_question_id = duplicate.id
                candidate.duplicate_question_stem_snapshot = duplicate.stem
                fatal = True

        if not fatal and candidate.stem:
            self._semantic_duplicate_check(candidate, previous_candidates, warnings)

        candidate.warnings = list(dict.fromkeys(warnings))
        if fatal:
            candidate.label = CandidateLabel.REJECTED.value
            candidate.status = CandidateStatus.VALIDATED.value
        elif warnings:
            candidate.label = CandidateLabel.NEED_REVIEW.value
            candidate.status = CandidateStatus.NEED_REVIEW.value
        else:
            candidate.label = CandidateLabel.GOOD.value
            candidate.status = CandidateStatus.VALIDATED.value

    def _semantic_duplicate_check(
        self,
        candidate: DocumentQuestionCandidate,
        previous_candidates: list[dict[str, Any]],
        warnings: list[str],
    ) -> None:
        candidate_vector = self._embed_for_duplicate(candidate.stem)
        threshold = (
            self.settings.validation_duplicate_real_e5_min
            if self.settings.embedding_provider == "real_e5"
            else self.settings.validation_duplicate_strong_min
        )
        best: dict[str, Any] | None = None
        if vector_index.ready:
            for item in vector_index.items.values():
                similarity = cosine_similarity(candidate_vector, item.vector)
                if self.settings.embedding_provider == "mock_deterministic":
                    similarity = min(0.99, 0.72 + max(similarity, 0.0) * 0.35)
                if best is None or similarity > best["similarity"]:
                    best = {
                        "id": item.question_id,
                        "stem": item.stem,
                        "similarity": similarity,
                        "warning": STRONG_DUPLICATE_WITH_EXISTING_QUESTION,
                    }
        else:
            warnings.append(VECTOR_INDEX_NOT_READY)

        for previous in previous_candidates:
            if not previous.get("vector"):
                continue
            similarity = cosine_similarity(candidate_vector, previous["vector"])
            if self.settings.embedding_provider == "mock_deterministic":
                similarity = min(0.99, 0.72 + max(similarity, 0.0) * 0.35)
            if best is None or similarity > best["similarity"]:
                best = {
                    "id": previous["id"],
                    "stem": previous["stem"],
                    "similarity": similarity,
                    "warning": DUPLICATE_WITH_DOCUMENT_CANDIDATE,
                }

        if best and best["similarity"] >= threshold:
            candidate.duplicate_max_similarity = best["similarity"]
            candidate.duplicate_question_id = best["id"]
            candidate.duplicate_question_stem_snapshot = best["stem"]
            warnings.append(best["warning"])
        elif best and best["similarity"] >= self.settings.validation_duplicate_review_min:
            candidate.duplicate_max_similarity = best["similarity"]
            candidate.duplicate_question_id = best["id"]
            candidate.duplicate_question_stem_snapshot = best["stem"]
            warnings.append(POSSIBLE_DUPLICATE_WITH_EXISTING_QUESTION)

    def _embed_for_duplicate(self, text: str) -> list[float]:
        return get_embedding_service(self.settings).embed_text(E5InputFormatter.format_for_e5(text))

    def _exact_bank_duplicate(self, normalized_stem: str) -> Question | None:
        questions = self.db.scalars(
            select(Question).where(Question.status == QuestionStatus.APPROVED.value)
        )
        for question in questions:
            if TextNormalizer.normalize_for_comparison(question.stem) == normalized_stem:
                return question
        return None

    def _previous_candidates(self, candidate: DocumentQuestionCandidate) -> list[dict[str, Any]]:
        items = list(
            self.db.scalars(
                select(DocumentQuestionCandidate)
                .where(
                    DocumentQuestionCandidate.job_id == candidate.job_id,
                    DocumentQuestionCandidate.id != candidate.id,
                )
                .order_by(DocumentQuestionCandidate.created_at)
            )
        )
        return [
            {"id": item.id, "stem": item.stem, "vector": self._embed_for_duplicate(item.stem)}
            for item in items
            if item.stem
        ]

    @staticmethod
    def _excerpt_matches_chunk(excerpt: str, chunk_text: str) -> bool:
        normalized_excerpt = TextNormalizer.normalize_for_comparison(excerpt)
        normalized_chunk = TextNormalizer.normalize_for_comparison(chunk_text)
        if normalized_excerpt and normalized_excerpt in normalized_chunk:
            return True
        excerpt_tokens = tokenize(excerpt)
        if not excerpt_tokens:
            return False
        chunk_tokens = tokenize(chunk_text)
        coverage = len(excerpt_tokens & chunk_tokens) / len(excerpt_tokens)
        return coverage >= 0.6


def _has_invalid_option_pattern(text: str) -> bool:
    normalized = TextNormalizer.normalize_for_comparison(text)
    raw = text.casefold()
    invalid_phrases = (
        "tất cả đều đúng",
        "tất cả các đáp án",
        "tất cả đáp án",
        "cả a và b",
        "cả b và c",
        "cả a b và c",
        "không có đáp án nào",
        "đáp án trên đều",
        "tat ca deu dung",
        "tat ca cac dap an",
        "tat ca dap an",
        "ca a va b",
        "ca b va c",
        "ca a b va c",
        "khong co dap an nao",
        "dap an tren deu",
    )
    if any(phrase in raw for phrase in invalid_phrases):
        return True
    return any(phrase in normalized for phrase in invalid_phrases)


def _coerce_quality_score(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, score))
