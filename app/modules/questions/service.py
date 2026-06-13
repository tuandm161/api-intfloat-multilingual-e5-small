"""Question bank business rules and serialization."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import ErrorCode, QuestionType
from app.core.errors import AppError
from app.db.models.question import Question
from app.modules.audit.service import AuditService
from app.modules.embeddings.vector_index import (
    embed_question,
)
from app.modules.questions.repository import QuestionRepository
from app.modules.questions.schemas import QuestionCreate, QuestionListQuery, QuestionUpdate


def question_to_dict(question: Question, paraphrase_count: int = 0) -> dict:
    return {
        "id": question.id,
        "stem": question.stem,
        "options": {
            "A": question.option_a,
            "B": question.option_b,
            "C": question.option_c,
            "D": question.option_d,
        },
        "correctAnswer": question.correct_answer,
        "explanation": question.explanation,
        "topic": question.topic,
        "difficulty": question.difficulty,
        "language": question.language,
        "sourceDocument": question.source_document,
        "questionType": question.question_type,
        "status": question.status,
        "parentQuestionId": question.parent_question_id,
        "paraphraseCount": paraphrase_count,
        "createdBy": question.created_by,
        "reviewedBy": question.reviewed_by,
        "createdAt": question.created_at,
        "updatedAt": question.updated_at,
    }


class QuestionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = QuestionRepository(db)
        self.audit = AuditService(db)

    def get_or_fail(self, question_id: str) -> Question:
        question = self.repository.get(question_id)
        if not question:
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"Không tìm thấy câu hỏi {question_id}",
                status_code=404,
            )
        return question

    def detail(self, question_id: str) -> dict:
        question = self.get_or_fail(question_id)
        return question_to_dict(question, len(self.repository.children(question_id)))

    def list(self, query: QuestionListQuery) -> dict:
        questions, total = self.repository.list(query)
        items = [
            question_to_dict(item, len(self.repository.children(item.id)))
            for item in questions
        ]
        return {
            "items": items,
            "page": query.page,
            "pageSize": query.page_size,
            "total": total,
        }

    def create(
        self,
        payload: QuestionCreate,
        settings: Settings,
        *,
        question_id: str | None = None,
    ) -> Question:
        if payload.question_type is QuestionType.ORIGINAL and payload.parent_question_id:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "Câu hỏi gốc không thể có câu hỏi cha",
                details={"field": "parentQuestionId"},
            )
        if payload.question_type is QuestionType.PARAPHRASE:
            if not payload.parent_question_id:
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    "Câu diễn đạt lại phải có câu hỏi cha",
                    details={"field": "parentQuestionId"},
                )
            parent = self.get_or_fail(payload.parent_question_id)
            if parent.parent_question_id == question_id:
                raise AppError(ErrorCode.VALIDATION_ERROR, "Quan hệ câu hỏi cha bị vòng lặp")
        identifier = question_id or f"Q-{uuid4().hex[:8].upper()}"
        if self.repository.get(identifier):
            raise AppError(
                ErrorCode.DUPLICATE_RESOURCE,
                f"Câu hỏi {identifier} đã tồn tại",
                status_code=409,
            )
        data = payload.model_dump(by_alias=False)
        data["language"] = payload.language.value
        data["question_type"] = payload.question_type.value
        data["status"] = payload.status.value
        question = Question(id=identifier, created_by="demo-user", **data)
        self.repository.add(question)
        embed_question(self.db, question, settings)
        self.audit.log(
            "Question",
            question.id,
            "QUESTION_CREATED",
            actor="demo-user",
            after={"stem": question.stem, "questionType": question.question_type},
        )
        self.db.commit()
        return question

    def update(self, question_id: str, payload: QuestionUpdate) -> Question:
        question = self.get_or_fail(question_id)
        before = question_to_dict(question, len(self.repository.children(question_id)))
        data = payload.model_dump(exclude_unset=True, by_alias=False)
        for name, value in data.items():
            if hasattr(value, "value"):
                value = value.value
            setattr(question, name, value)
        self.audit.log(
            "Question",
            question.id,
            "QUESTION_UPDATED",
            actor="demo-user",
            before=before,
            after={"updatedFields": list(data)},
        )
        self.db.commit()
        return question

    def paraphrases(self, question_id: str) -> list[dict]:
        self.get_or_fail(question_id)
        return [question_to_dict(item) for item in self.repository.children(question_id)]
