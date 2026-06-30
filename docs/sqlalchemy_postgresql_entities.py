"""PostgreSQL-ready SQLAlchemy 2.0 entities for the question bank domain.

Copy this file into the main project if it also uses Python/FastAPI/SQLAlchemy.
The schema mirrors the current demo app but uses PostgreSQL JSONB and ARRAY
types instead of SQLite-compatible JSON columns.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Question(Base, TimestampMixin):
    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint("correct_answer IN ('A', 'B', 'C', 'D')", name="ck_questions_correct_answer"),
        CheckConstraint("language IN ('vi', 'en', 'bilingual')", name="ck_questions_language"),
        CheckConstraint("question_type IN ('ORIGINAL', 'PARAPHRASE')", name="ck_questions_type"),
        CheckConstraint(
            "status IN ('DRAFT', 'APPROVED', 'REJECTED', 'ARCHIVED')",
            name="ck_questions_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    option_a: Mapped[str] = mapped_column(Text, nullable=False)
    option_b: Mapped[str] = mapped_column(Text, nullable=False)
    option_c: Mapped[str] = mapped_column(Text, nullable=False)
    option_d: Mapped[str] = mapped_column(Text, nullable=False)
    correct_answer: Mapped[str] = mapped_column(String(1), nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(String(255), index=True)
    difficulty: Mapped[str | None] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(16), default="vi", nullable=False)
    source_document: Mapped[str | None] = mapped_column(String(255))
    question_type: Mapped[str] = mapped_column(String(16), default="ORIGINAL", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="APPROVED", nullable=False, index=True)
    parent_question_id: Mapped[str | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL"), index=True
    )
    created_by: Mapped[str | None] = mapped_column(String(100))
    reviewed_by: Mapped[str | None] = mapped_column(String(100))

    parent: Mapped[Question | None] = relationship(
        remote_side="Question.id", back_populates="children"
    )
    children: Mapped[list[Question]] = relationship(back_populates="parent")
    embeddings: Mapped[list[QuestionEmbedding]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )
    exam_links: Mapped[list[ExamQuestion]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )


class QuestionEmbedding(Base):
    __tablename__ = "question_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "question_id",
            "text_type",
            "embedding_model",
            "input_text_hash",
            name="uq_question_embeddings_input",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    text_type: Mapped[str] = mapped_column(String(32), default="stem", nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    input_text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    vector: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    question: Mapped[Question] = relationship(back_populates="embeddings")


class ParaphraseJob(Base, TimestampMixin):
    __tablename__ = "paraphrase_jobs"
    __table_args__ = (
        CheckConstraint("mode IN ('STEM_ONLY')", name="ck_paraphrase_jobs_mode"),
        CheckConstraint("provider IN ('mock', 'api', 'local')", name="ck_paraphrase_jobs_provider"),
        CheckConstraint(
            "status IN ('CREATED', 'GENERATING', 'GENERATED', 'VALIDATING', 'COMPLETED', 'FAILED')",
            name="ck_paraphrase_jobs_status",
        ),
        CheckConstraint("requested_count BETWEEN 1 AND 10", name="ck_paraphrase_jobs_requested_count"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    mode: Mapped[str] = mapped_column(String(32), default="STEM_ONLY", nullable=False)
    target_language: Mapped[str] = mapped_column(String(16), default="vi", nullable=False)
    requested_count: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    change_strength: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    provider: Mapped[str] = mapped_column(String(16), default="mock", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="CREATED", nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(100))

    source_question: Mapped[Question] = relationship()
    candidates: Mapped[list[ParaphraseCandidate]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class ParaphraseCandidate(Base, TimestampMixin):
    __tablename__ = "paraphrase_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('GENERATED', 'VALIDATED', 'NEED_REVIEW', 'APPROVED', 'REJECTED', 'SAVED')",
            name="ck_paraphrase_candidates_status",
        ),
        CheckConstraint(
            "label IS NULL OR label IN ('GOOD', 'NEED_REVIEW', 'REJECTED')",
            name="ck_paraphrase_candidates_label",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("paraphrase_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    candidate_stem: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_candidate_stem: Mapped[str] = mapped_column(Text, nullable=False)
    semantic_similarity_to_source: Mapped[float | None] = mapped_column(Float)
    lexical_difference_from_source: Mapped[float | None] = mapped_column(Float)
    duplicate_max_similarity: Mapped[float | None] = mapped_column(Float)
    duplicate_question_id: Mapped[str | None] = mapped_column(String(64))
    duplicate_question_stem_snapshot: Mapped[str | None] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(String(20))
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="GENERATED", nullable=False, index=True)
    reviewer_notes: Mapped[str | None] = mapped_column(Text)

    job: Mapped[ParaphraseJob] = relationship(back_populates="candidates")
    source_question: Mapped[Question] = relationship()


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("status IN ('READY', 'OCR_REQUIRED', 'FAILED')", name="ck_documents_status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32), default="READY", nullable=False, index=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(100))

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
    )
    sections: Mapped[list[DocumentSection]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentSection.order_index",
    )
    question_jobs: Mapped[list[DocumentQuestionJob]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentSection(Base):
    __tablename__ = "document_sections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_sections.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="sections")
    parent: Mapped[DocumentSection | None] = relationship(remote_side=[id])


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_position"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    section_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_sections.id", ondelete="SET NULL"), index=True
    )
    parent_chunk_id: Mapped[str | None] = mapped_column(String(64))
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    chunk_type: Mapped[str] = mapped_column(String(32), default="generation", nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(String(255))
    section_path: Mapped[str | None] = mapped_column(String(1000))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quality_flags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    previous_chunk_id: Mapped[str | None] = mapped_column(String(64))
    next_chunk_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="chunks")
    section: Mapped[DocumentSection | None] = relationship()
    question_candidates: Mapped[list[DocumentQuestionCandidate]] = relationship(back_populates="chunk")
    knowledge_points: Mapped[list[DocumentKnowledgePoint]] = relationship(
        back_populates="chunk", cascade="all, delete-orphan"
    )


class DocumentQuestionJob(Base, TimestampMixin):
    __tablename__ = "document_question_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CREATED', 'GENERATING', 'GENERATED', 'PARTIALLY_COMPLETED', 'FAILED')",
            name="ck_document_question_jobs_status",
        ),
        CheckConstraint("questions_per_chunk BETWEEN 1 AND 5", name="ck_document_question_jobs_qpc"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), default="api", nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="CREATED", nullable=False, index=True)
    questions_per_chunk: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    llm_call_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(100))

    document: Mapped[Document] = relationship(back_populates="question_jobs")
    candidates: Mapped[list[DocumentQuestionCandidate]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    knowledge_points: Mapped[list[DocumentKnowledgePoint]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class DocumentKnowledgePoint(Base):
    __tablename__ = "document_knowledge_points"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("document_question_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_key: Mapped[str | None] = mapped_column(String(64))
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    knowledge_type: Mapped[str | None] = mapped_column(String(64))
    importance: Mapped[str | None] = mapped_column(String(32))
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    generation_eligible: Mapped[bool] = mapped_column(default=True, nullable=False)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped[DocumentQuestionJob] = relationship(back_populates="knowledge_points")
    chunk: Mapped[DocumentChunk] = relationship(back_populates="knowledge_points")


class DocumentQuestionCandidate(Base, TimestampMixin):
    __tablename__ = "document_question_candidates"
    __table_args__ = (
        CheckConstraint("correct_answer IN ('A', 'B', 'C', 'D')", name="ck_document_candidates_answer"),
        CheckConstraint(
            "status IN ('GENERATED', 'VALIDATED', 'NEED_REVIEW', 'APPROVED', 'REJECTED', 'SAVED')",
            name="ck_document_candidates_status",
        ),
        CheckConstraint(
            "label IS NULL OR label IN ('GOOD', 'NEED_REVIEW', 'REJECTED')",
            name="ck_document_candidates_label",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("document_question_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    option_a: Mapped[str] = mapped_column(Text, nullable=False)
    option_b: Mapped[str] = mapped_column(Text, nullable=False)
    option_c: Mapped[str] = mapped_column(Text, nullable=False)
    option_d: Mapped[str] = mapped_column(Text, nullable=False)
    correct_answer: Mapped[str] = mapped_column(String(1), nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(String(255))
    difficulty: Mapped[str | None] = mapped_column(String(32))
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    generation_key: Mapped[str | None] = mapped_column(String(128), index=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Float)
    llm_validation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    label: Mapped[str | None] = mapped_column(String(20))
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="GENERATED", nullable=False, index=True)
    duplicate_max_similarity: Mapped[float | None] = mapped_column(Float)
    duplicate_question_id: Mapped[str | None] = mapped_column(String(64))
    duplicate_question_stem_snapshot: Mapped[str | None] = mapped_column(Text)
    reviewer_notes: Mapped[str | None] = mapped_column(Text)
    saved_question_id: Mapped[str | None] = mapped_column(String(64), index=True)

    job: Mapped[DocumentQuestionJob] = relationship(back_populates="candidates")
    chunk: Mapped[DocumentChunk] = relationship(back_populates="question_candidates")


class Exam(Base, TimestampMixin):
    __tablename__ = "exams"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(100), default="demo-user", nullable=False)

    question_links: Mapped[list[ExamQuestion]] = relationship(
        back_populates="exam",
        cascade="all, delete-orphan",
        order_by="ExamQuestion.position",
    )


class ExamQuestion(Base):
    __tablename__ = "exam_questions"
    __table_args__ = (
        UniqueConstraint("exam_id", "question_id", name="uq_exam_questions_exam_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_id: Mapped[str] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), index=True, nullable=False
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    exam: Mapped[Exam] = relationship(back_populates="question_links")
    question: Mapped[Question] = relationship(back_populates="exam_links")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(100), default="system", nullable=False)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
