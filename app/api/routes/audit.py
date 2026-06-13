"""Audit log API routes."""

from fastapi import APIRouter, Query

from app.api.dependencies import DbSession
from app.core.responses import success_response
from app.modules.audit.service import AuditService

router = APIRouter(tags=["audit"])


@router.get("/audit-logs")
def list_audit_logs(
    db: DbSession,
    entity_type: str | None = Query(None, alias="entityType"),
    entity_id: str | None = Query(None, alias="entityId"),
    action: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
) -> dict:
    return success_response(
        AuditService(db).list(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/questions/{question_id}/audit-logs")
def question_audit_logs(question_id: str, db: DbSession) -> dict:
    return success_response(
        AuditService(db).list(entity_type="Question", entity_id=question_id)
    )
