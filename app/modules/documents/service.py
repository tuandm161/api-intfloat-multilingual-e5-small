"""Document ingestion, chunking, generation, and review workflow."""

from typing import Any
from uuid import uuid4

from sqlalchemy import select
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
    DocumentQuestionCandidate,
    DocumentQuestionJob,
)
from app.db.models.question import Question
from app.modules.audit.service import AuditService
from app.modules.documents.extractors import extract_pages
from app.modules.documents.processing import clean_pages, split_into_chunks
from app.modules.documents.providers import (
    DeepSeekDocumentQuestionGenerator,
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
        data["chunks"] = [chunk_to_dict(chunk) for chunk in document.chunks]
        data["questionJobs"] = [job_to_dict(job) for job in document.question_jobs]
    return data


def chunk_to_dict(chunk: DocumentChunk) -> dict:
    return {
        "id": chunk.id,
        "documentId": chunk.document_id,
        "chunkIndex": chunk.chunk_index,
        "pageStart": chunk.page_start,
        "pageEnd": chunk.page_end,
        "sectionTitle": chunk.section_title,
        "text": chunk.text,
        "textHash": chunk.text_hash,
        "charCount": chunk.char_count,
    }


def job_to_dict(job: DocumentQuestionJob, *, include_candidates: bool = False) -> dict:
    data = {
        "id": job.id,
        "documentId": job.document_id,
        "provider": job.provider,
        "model": job.model,
        "status": job.status,
        "questionsPerChunk": job.questions_per_chunk,
        "chunkCount": job.chunk_count,
        "candidateCount": job.candidate_count,
        "errorMessage": job.error_message,
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
    }
    if include_candidates:
        data["candidates"] = [candidate_to_dict(candidate) for candidate in job.candidates]
    return data


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
        for chunk in chunks:
            self.db.add(
                DocumentChunk(
                    id=f"CH-{uuid4().hex[:8].upper()}",
                    document_id=document.id,
                    chunk_index=chunk.chunk_index,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section_title=chunk.section_title,
                    text=chunk.text,
                    text_hash=chunk.text_hash,
                    char_count=len(chunk.text),
                )
            )
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
            for chunk in document.chunks:
                raw_questions = generator.generate_questions(
                    chunk_text=chunk.text,
                    questions_per_chunk=count,
                    target_language="vi",
                )
                for raw in raw_questions:
                    candidate = self._candidate_from_raw(job, chunk, raw)
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
            job.status = "GENERATED"
            job.candidate_count = len(job.candidates)
            self.audit.log(
                "DocumentQuestionJob",
                job.id,
                "DOCUMENT_QUESTION_CANDIDATES_GENERATED",
                actor="demo-user",
                after={"candidateCount": job.candidate_count},
            )
            self.db.commit()
            return job_to_dict(job, include_candidates=True)
        except Exception as exc:
            job.status = "FAILED"
            job.error_message = str(exc)
            for candidate in list(job.candidates):
                self.db.delete(candidate)
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
