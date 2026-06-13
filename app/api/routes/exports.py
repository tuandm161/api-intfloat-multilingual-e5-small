"""Approved question bank export routes."""

import csv
import io

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.dependencies import DbSession
from app.core.enums import QuestionStatus, QuestionType
from app.core.responses import success_response
from app.db.models.question import Question
from app.modules.audit.service import AuditService

router = APIRouter(prefix="/exports", tags=["exports"])
EXPORT_COLUMNS = [
    "id", "stem", "option_a", "option_b", "option_c", "option_d",
    "correct_answer", "explanation", "topic", "difficulty", "language",
    "question_type", "parent_question_id", "status",
]


def export_rows(
    db,
    question_type: QuestionType | None,
    status: QuestionStatus,
    parent_question_id: str | None,
) -> list[dict]:
    statement = select(Question).where(Question.status == status.value)
    if question_type:
        statement = statement.where(Question.question_type == question_type.value)
    if parent_question_id:
        statement = statement.where(Question.parent_question_id == parent_question_id)
    questions = list(db.scalars(statement.order_by(Question.id)))
    return [{column: getattr(item, column) for column in EXPORT_COLUMNS} for item in questions]


@router.get("/questions.json")
def export_json(
    db: DbSession,
    question_type: QuestionType | None = Query(None, alias="questionType"),
    status: QuestionStatus = QuestionStatus.APPROVED,
    parent_question_id: str | None = Query(None, alias="parentQuestionId"),
) -> dict:
    rows = export_rows(db, question_type, status, parent_question_id)
    AuditService(db).log("Question", "export", "EXPORT_CREATED", actor="demo-user", after={"format": "json", "count": len(rows)})
    db.commit()
    return success_response({"items": rows, "count": len(rows)})


@router.get("/questions.csv")
def export_csv(
    db: DbSession,
    question_type: QuestionType | None = Query(None, alias="questionType"),
    status: QuestionStatus = QuestionStatus.APPROVED,
    parent_question_id: str | None = Query(None, alias="parentQuestionId"),
) -> StreamingResponse:
    rows = export_rows(db, question_type, status, parent_question_id)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    AuditService(db).log("Question", "export", "EXPORT_CREATED", actor="demo-user", after={"format": "csv", "count": len(rows)})
    db.commit()
    content = output.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=questions.csv"},
    )
