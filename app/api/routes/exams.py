"""Exam assembly API and server-rendered pages."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.api.dependencies import DbSession, SettingsDependency
from app.api.templates import templates
from app.core.responses import success_response
from app.modules.exams.schemas import ExamCreate, ExamQuestionAdd
from app.modules.exams.service import ExamService, exam_to_dict

router = APIRouter(prefix="/exams", tags=["exams"])


def wants_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "")


@router.get("")
def list_exams(request: Request, db: DbSession, settings: SettingsDependency):
    items = ExamService(db, settings).list_exams()
    if wants_html(request):
        return templates.TemplateResponse(
            request=request,
            name="exams.html",
            context={"title": "Bộ đề", "active_page": "exams", "items": items},
        )
    return success_response({"items": items})


@router.get("/new", response_class=HTMLResponse)
def new_exam_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="exam_new.html",
        context={"title": "Tạo bộ đề", "active_page": "exams"},
    )


@router.post("", status_code=201)
def create_exam(payload: ExamCreate, db: DbSession, settings: SettingsDependency) -> dict:
    return success_response(
        exam_to_dict(ExamService(db, settings).create(payload.title, payload.description))
    )


@router.get("/{exam_id}")
def get_exam(exam_id: str, request: Request, db: DbSession, settings: SettingsDependency):
    service = ExamService(db, settings)
    exam = service.get_or_fail(exam_id)
    data = exam_to_dict(exam)
    if wants_html(request):
        return templates.TemplateResponse(
            request=request,
            name="exam_detail.html",
            context={
                "title": exam.title,
                "active_page": "exams",
                "exam": data,
                "available_questions": service.available_questions(exam_id),
            },
        )
    return success_response(data)


@router.post("/{exam_id}/questions", status_code=201)
def add_exam_question(
    exam_id: str,
    payload: ExamQuestionAdd,
    db: DbSession,
    settings: SettingsDependency,
) -> dict:
    return success_response(ExamService(db, settings).add_question(exam_id, payload.questionId))


@router.delete("/{exam_id}/questions/{question_id}")
def remove_exam_question(
    exam_id: str,
    question_id: str,
    db: DbSession,
    settings: SettingsDependency,
) -> dict:
    return success_response(ExamService(db, settings).remove_question(exam_id, question_id))
