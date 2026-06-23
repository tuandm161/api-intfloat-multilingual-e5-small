"""Paraphrase job API routes."""

from fastapi import APIRouter, Request

from app.api.dependencies import DbSession, SettingsDependency
from app.api.templates import templates
from app.core.responses import success_response
from app.modules.paraphrase.schemas import ParaphraseJobCreate
from app.modules.paraphrase.service import ParaphraseService

router = APIRouter(prefix="/paraphrase-jobs", tags=["paraphrase"])
@router.get("")
def list_jobs(request: Request, db: DbSession):
    items = ParaphraseService(db).list_jobs()
    if "text/html" in request.headers.get("accept", ""):
        return templates.TemplateResponse(
            request=request,
            name="jobs.html",
            context={"title": "Lịch sử diễn đạt lại", "active_page": "jobs", "items": items},
        )
    return success_response({"items": items})


@router.post("", status_code=201)
def create_job(payload: ParaphraseJobCreate, db: DbSession, settings: SettingsDependency) -> dict:
    return success_response(ParaphraseService(db, settings).create_job(payload))


@router.get("/{job_id}")
def get_job(job_id: str, request: Request, db: DbSession):
    data = ParaphraseService(db).detail(job_id)
    if "text/html" in request.headers.get("accept", ""):
        return templates.TemplateResponse(
            request=request,
            name="job_detail.html",
            context={
                "title": f"Phiên diễn đạt lại {job_id}",
                "active_page": "jobs",
                "job": data,
            },
        )
    return success_response(data)


@router.post("/{job_id}/retry", status_code=201)
def retry_job(job_id: str, db: DbSession, settings: SettingsDependency) -> dict:
    return success_response(ParaphraseService(db, settings).retry_job(job_id))
