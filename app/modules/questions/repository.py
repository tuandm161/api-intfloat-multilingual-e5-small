"""Question persistence operations."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models.question import Question
from app.modules.questions.schemas import QuestionListQuery


class QuestionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, question_id: str) -> Question | None:
        return self.db.get(Question, question_id)

    def list(self, query: QuestionListQuery) -> tuple[list[Question], int]:
        statement = select(Question)
        count_statement = select(func.count()).select_from(Question)
        filters = []
        if query.search:
            pattern = f"%{query.search}%"
            filters.append(or_(Question.stem.ilike(pattern), Question.topic.ilike(pattern)))
        if query.topic:
            filters.append(Question.topic == query.topic)
        if query.status:
            filters.append(Question.status == query.status.value)
        if query.question_type:
            filters.append(Question.question_type == query.question_type.value)
        if query.parent_question_id:
            filters.append(Question.parent_question_id == query.parent_question_id)
        if filters:
            statement = statement.where(*filters)
            count_statement = count_statement.where(*filters)
        statement = statement.order_by(Question.id).offset(
            (query.page - 1) * query.page_size
        ).limit(query.page_size)
        return list(self.db.scalars(statement)), self.db.scalar(count_statement) or 0

    def children(self, question_id: str) -> list[Question]:
        return list(
            self.db.scalars(
                select(Question)
                .where(Question.parent_question_id == question_id)
                .order_by(Question.created_at)
            )
        )

    def add(self, question: Question) -> Question:
        self.db.add(question)
        self.db.flush()
        return question
