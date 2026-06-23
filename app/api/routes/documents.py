"""Document upload, chunking, generation, and review routes."""

from fastapi import APIRouter, File, Request, UploadFile

from app.api.dependencies import DbSession, SettingsDependency
from app.api.templates import templates
from app.core.responses import success_response
from app.modules.documents.schemas import (
    DocumentQuestionCandidateEdit,
    DocumentQuestionJobCreate,
    DocumentReviewRequest,
)
from app.modules.documents.service import (
    DocumentService,
    candidate_to_dict,
    job_to_dict,
)

router = APIRouter(tags=["documents"])


def wants_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "")


@router.get("/documents")
def list_documents(request: Request, db: DbSession, settings: SettingsDependency):
    items = DocumentService(db, settings).list_documents()
    if wants_html(request):
        return templates.TemplateResponse(
            request=request,
            name="documents.html",
            context={"title": "Tài liệu", "active_page": "documents", "items": items},
        )
    return success_response({"items": items})


@router.post("/documents", status_code=201)
async def upload_document(
    request: Request,
    db: DbSession,
    settings: SettingsDependency,
    file: UploadFile = File(...),
):
    content = await file.read()
    data = DocumentService(db, settings).upload_document(
        filename=file.filename or "document.txt",
        content_type=file.content_type,
        content=content,
    )
    if wants_html(request):
        return templates.TemplateResponse(
            request=request,
            name="document_detail.html",
            context={"title": data["filename"], "active_page": "documents", "document": data},
            status_code=201,
        )
    return success_response(data)


@router.get("/documents/{document_id}")
def get_document(document_id: str, request: Request, db: DbSession, settings: SettingsDependency):
    data = DocumentService(db, settings).detail(document_id)
    if wants_html(request):
        return templates.TemplateResponse(
            request=request,
            name="document_detail.html",
            context={"title": data["filename"], "active_page": "documents", "document": data},
        )
    return success_response(data)


@router.post("/documents/{document_id}/question-jobs", status_code=201)
def create_document_question_job(
    document_id: str,
    payload: DocumentQuestionJobCreate,
    db: DbSession,
    settings: SettingsDependency,
) -> dict:
    return success_response(
        DocumentService(db, settings).create_question_job(
            document_id,
            questions_per_chunk=payload.questions_per_chunk,
        )
    )


@router.get("/document-question-jobs/{job_id}")
def get_document_question_job(job_id: str, request: Request, db: DbSession, settings: SettingsDependency):
    job = DocumentService(db, settings).get_job_or_fail(job_id)
    data = job_to_dict(job, include_candidates=True)
    if wants_html(request):
        return templates.TemplateResponse(
            request=request,
            name="document_job_detail.html",
            context={"title": f"Phiên tạo câu hỏi {job_id}", "active_page": "documents", "job": data},
        )
    return success_response(data)


@router.get("/document-question-candidates/{candidate_id}")
def get_document_question_candidate(candidate_id: str, db: DbSession, settings: SettingsDependency) -> dict:
    return success_response(
        candidate_to_dict(DocumentService(db, settings).get_candidate_or_fail(candidate_id))
    )


@router.put("/document-question-candidates/{candidate_id}")
def edit_document_question_candidate(
    candidate_id: str,
    payload: DocumentQuestionCandidateEdit,
    db: DbSession,
    settings: SettingsDependency,
) -> dict:
    return success_response(DocumentService(db, settings).edit_candidate(candidate_id, payload))


@router.post("/document-question-candidates/{candidate_id}/approve")
def approve_document_question_candidate(
    candidate_id: str,
    payload: DocumentReviewRequest,
    db: DbSession,
    settings: SettingsDependency,
) -> dict:
    return success_response(
        DocumentService(db, settings).approve_candidate(candidate_id, payload.reviewerNotes)
    )


@router.post("/document-question-candidates/{candidate_id}/reject")
def reject_document_question_candidate(
    candidate_id: str,
    payload: DocumentReviewRequest,
    db: DbSession,
    settings: SettingsDependency,
) -> dict:
    return success_response(
        DocumentService(db, settings).reject_candidate(candidate_id, payload.reviewerNotes)
    )


@router.post("/document-question-candidates/{candidate_id}/save-as-question")
def save_document_question_candidate(
    candidate_id: str,
    db: DbSession,
    settings: SettingsDependency,
) -> dict:
    return success_response(DocumentService(db, settings).save_candidate_as_question(candidate_id))
