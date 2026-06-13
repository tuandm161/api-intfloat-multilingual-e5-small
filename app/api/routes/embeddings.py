"""Embedding and duplicate-search API routes."""

from pydantic import BaseModel, Field
from fastapi import APIRouter

from app.api.dependencies import DbSession, SettingsDependency
from app.core.responses import success_response
from app.modules.embeddings.vector_index import (
    embedding_status,
    get_embedding_service,
    rebuild_index,
    vector_index,
)
from app.modules.normalization.text_builders import E5InputFormatter

router = APIRouter(tags=["embeddings"])


class DuplicateSearchRequest(BaseModel):
    text: str = Field(min_length=1)
    topK: int = Field(default=5, ge=1, le=50)
    excludeQuestionIds: list[str] = Field(default_factory=list)


@router.post("/embeddings/reindex")
def reindex(db: DbSession, settings: SettingsDependency) -> dict:
    result = rebuild_index(db, settings)
    return success_response(result)


@router.get("/embeddings/status")
def status(db: DbSession, settings: SettingsDependency) -> dict:
    return success_response(embedding_status(db, settings))


@router.post("/duplicates/search")
def duplicate_search(
    payload: DuplicateSearchRequest,
    settings: SettingsDependency,
) -> dict:
    vector = get_embedding_service(settings).embed_text(
        E5InputFormatter.format_for_e5(payload.text)
    )
    items = vector_index.search_similar(
        vector, payload.topK, payload.excludeQuestionIds
    )
    return success_response({"items": items, "indexReady": vector_index.ready})
