"""Exam assembly and within-exam semantic duplicate prevention."""

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import ErrorCode, QuestionStatus
from app.core.errors import AppError
from app.db.models.exam import Exam, ExamQuestion
from app.db.models.question import Question
from app.modules.audit.service import AuditService
from app.modules.embeddings.interfaces import cosine_similarity
from app.modules.embeddings.vector_index import get_embedding_service, vector_index
from app.modules.normalization.text_builders import E5InputFormatter
from app.modules.normalization.text_normalizer import TextNormalizer
from app.modules.questions.service import question_to_dict


def exam_to_dict(exam: Exam) -> dict:
    return {
        "id": exam.id,
        "title": exam.title,
        "description": exam.description,
        "questionCount": len(exam.question_links),
        "questions": [question_to_dict(link.question) for link in exam.question_links],
        "createdAt": exam.created_at,
        "updatedAt": exam.updated_at,
    }


class ExamService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.audit = AuditService(db)

    def get_or_fail(self, exam_id: str) -> Exam:
        exam = self.db.get(Exam, exam_id)
        if not exam:
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"Không tìm thấy bộ đề {exam_id}",
                status_code=404,
            )
        return exam

    def list_exams(self) -> list[dict]:
        exams = list(self.db.scalars(select(Exam).order_by(Exam.created_at.desc())))
        return [exam_to_dict(exam) for exam in exams]

    def create(self, title: str, description: str | None) -> Exam:
        exam = Exam(
            id=f"EX-{uuid4().hex[:8].upper()}",
            title=title.strip(),
            description=description.strip() if description else None,
            created_by="demo-user",
        )
        self.db.add(exam)
        self.audit.log(
            "Exam",
            exam.id,
            "EXAM_CREATED",
            actor="demo-user",
            after={"title": exam.title},
        )
        self.db.commit()
        return exam

    def available_questions(self, exam_id: str) -> list[dict]:
        exam = self.get_or_fail(exam_id)
        selected_ids = {link.question_id for link in exam.question_links}
        questions = list(
            self.db.scalars(
                select(Question)
                .where(Question.status == QuestionStatus.APPROVED.value)
                .order_by(Question.id)
            )
        )
        return [question_to_dict(item) for item in questions if item.id not in selected_ids]

    def _duplicate_in_exam(self, exam: Exam, candidate: Question) -> dict | None:
        if not exam.question_links:
            return None
        if not vector_index.ready:
            raise AppError(
                ErrorCode.VECTOR_INDEX_FAILED,
                "Chưa thể kiểm tra trùng vì chỉ mục tương đồng chưa sẵn sàng",
                status_code=503,
            )

        normalized = TextNormalizer.normalize_for_comparison(candidate.stem)
        for link in exam.question_links:
            if TextNormalizer.normalize_for_comparison(link.question.stem) == normalized:
                return {
                    "questionId": link.question.id,
                    "stem": link.question.stem,
                    "similarity": 1.0,
                    "matchType": "EXACT",
                }

        service = get_embedding_service(self.settings)
        candidate_vector = service.embed_text(E5InputFormatter.format_for_e5(candidate.stem))
        threshold = (
            self.settings.validation_duplicate_real_e5_min
            if self.settings.embedding_provider == "real_e5"
            else self.settings.validation_duplicate_strong_min
        )
        best: dict | None = None
        for link in exam.question_links:
            item = vector_index.items.get(link.question_id)
            if not item:
                continue
            similarity = cosine_similarity(candidate_vector, item.vector)
            if self.settings.embedding_provider == "mock_deterministic":
                similarity = min(0.99, 0.72 + max(similarity, 0.0) * 0.35)
            if best is None or similarity > best["similarity"]:
                best = {
                    "questionId": link.question.id,
                    "stem": link.question.stem,
                    "similarity": similarity,
                    "matchType": "SEMANTIC",
                }
        return best if best and best["similarity"] >= threshold else None

    def add_question(self, exam_id: str, question_id: str) -> dict:
        exam = self.get_or_fail(exam_id)
        question = self.db.get(Question, question_id)
        if not question:
            raise AppError(ErrorCode.NOT_FOUND, f"Không tìm thấy câu hỏi {question_id}", status_code=404)
        if any(link.question_id == question_id for link in exam.question_links):
            raise AppError(
                ErrorCode.DUPLICATE_RESOURCE,
                "Câu hỏi đã có trong bộ đề",
                status_code=409,
            )

        duplicate = self._duplicate_in_exam(exam, question)
        if duplicate:
            raise AppError(
                ErrorCode.DUPLICATE_RESOURCE,
                f"Câu hỏi có thể trùng ngữ nghĩa với {duplicate['questionId']} trong bộ đề",
                status_code=409,
                details={
                    "duplicateQuestionId": duplicate["questionId"],
                    "duplicateQuestionStem": duplicate["stem"],
                    "similarity": round(duplicate["similarity"], 4),
                    "matchType": duplicate["matchType"],
                },
            )

        position = (self.db.scalar(select(func.max(ExamQuestion.position)).where(ExamQuestion.exam_id == exam.id)) or 0) + 1
        self.db.add(ExamQuestion(exam_id=exam.id, question_id=question.id, position=position))
        self.audit.log(
            "Exam",
            exam.id,
            "EXAM_QUESTION_ADDED",
            actor="demo-user",
            after={"questionId": question.id, "position": position},
        )
        self.db.commit()
        return {"examId": exam.id, "questionId": question.id, "position": position}

    def remove_question(self, exam_id: str, question_id: str) -> dict:
        exam = self.get_or_fail(exam_id)
        link = self.db.scalar(
            select(ExamQuestion).where(
                ExamQuestion.exam_id == exam.id,
                ExamQuestion.question_id == question_id,
            )
        )
        if not link:
            raise AppError(ErrorCode.NOT_FOUND, "Câu hỏi không có trong bộ đề", status_code=404)
        self.db.delete(link)
        self.audit.log(
            "Exam",
            exam.id,
            "EXAM_QUESTION_REMOVED",
            actor="demo-user",
            before={"questionId": question_id},
        )
        self.db.commit()
        return {"examId": exam.id, "questionId": question_id}
