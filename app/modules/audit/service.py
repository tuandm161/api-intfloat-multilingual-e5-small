"""Audit logging and query service."""

from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def log(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        *,
        actor: str = "system",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> AuditLog:
        record = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor=actor,
            before_json=jsonable_encoder(before) if before is not None else None,
            after_json=jsonable_encoder(after) if after is not None else None,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def list(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        action: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        filters = []
        if entity_type:
            filters.append(AuditLog.entity_type == entity_type)
        if entity_id:
            filters.append(AuditLog.entity_id == entity_id)
        if action:
            filters.append(AuditLog.action == action)
        statement = select(AuditLog)
        count_statement = select(func.count()).select_from(AuditLog)
        if filters:
            statement = statement.where(*filters)
            count_statement = count_statement.where(*filters)
        records = list(
            self.db.scalars(
                statement.order_by(AuditLog.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return {
            "items": [
                {
                    "id": item.id,
                    "entityType": item.entity_type,
                    "entityId": item.entity_id,
                    "action": item.action,
                    "actor": item.actor,
                    "before": item.before_json,
                    "after": item.after_json,
                    "createdAt": item.created_at,
                }
                for item in records
            ],
            "page": page,
            "pageSize": page_size,
            "total": self.db.scalar(count_statement) or 0,
        }
