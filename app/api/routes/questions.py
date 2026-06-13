"""Question bank API routes."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from app.api.dependencies import DbSession, SettingsDependency
from app.api.templates import templates
from app.core.enums import QuestionStatus, QuestionType
from app.core.responses import success_response
from app.modules.questions.schemas import QuestionCreate, QuestionListQuery, QuestionUpdate
from app.modules.questions.service import QuestionService, question_to_dict

router = APIRouter(prefix="/questions", tags=["questions"])
def wants_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "")


@router.get("")
def list_questions(
    request: Request,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    search: str | None = None,
    topic: str | None = None,
    status: QuestionStatus | None = None,
    question_type: QuestionType | None = Query(None, alias="questionType"),
    parent_question_id: str | None = Query(None, alias="parentQuestionId"),
) -> dict:
    query = QuestionListQuery(
        page=page,
        pageSize=page_size,
        search=search,
        topic=topic,
        status=status,
        questionType=question_type,
        parentQuestionId=parent_question_id,
    )
    data = QuestionService(db).list(query)
    if wants_html(request):
        return templates.TemplateResponse(
            request=request,
            name="questions.html",
            context={"title": "Ngân hàng câu hỏi", "active_page": "questions", **data},
        )
    return success_response(data)


@router.get("/new", response_class=HTMLResponse)
def new_question_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="question_new.html",
        context={"title": "Tạo câu hỏi mới", "active_page": "questions"},
    )


@router.get("/{question_id}")
def get_question(question_id: str, request: Request, db: DbSession):
    service = QuestionService(db)
    data = service.detail(question_id)
    if wants_html(request):
        return templates.TemplateResponse(
            request=request,
            name="question_detail.html",
            context={
                "title": f"Câu hỏi {question_id}",
                "active_page": "questions",
                "question": data,
                "paraphrases": service.paraphrases(question_id),
            },
        )
    return success_response(data)


@router.post("", status_code=201)
def create_question(
    payload: QuestionCreate,
    db: DbSession,
    settings: SettingsDependency,
) -> dict:
    return success_response(
        question_to_dict(QuestionService(db).create(payload, settings))
    )


@router.put("/{question_id}")
def update_question(question_id: str, payload: QuestionUpdate, db: DbSession) -> dict:
    return success_response(
        question_to_dict(QuestionService(db).update(question_id, payload))
    )


@router.get("/{question_id}/paraphrases")
def list_paraphrases(question_id: str, db: DbSession) -> dict:
    return success_response({"items": QuestionService(db).paraphrases(question_id)})
