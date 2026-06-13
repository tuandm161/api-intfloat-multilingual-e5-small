"""Embedding orchestration and in-memory vector index."""

from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import QuestionStatus
from app.db.models.embedding import QuestionEmbedding
from app.db.models.audit_log import AuditLog
from app.db.models.question import Question
from app.modules.embeddings.e5_service import E5EmbeddingService
from app.modules.embeddings.interfaces import EmbeddingService, cosine_similarity
from app.modules.embeddings.mock_service import MockDeterministicEmbeddingService
from app.modules.normalization.text_builders import E5InputFormatter, QuestionTextBuilder
from app.modules.normalization.text_normalizer import TextNormalizer, hash_normalized_text


@dataclass
class IndexItem:
    question_id: str
    stem: str
    topic: str | None
    question_type: str
    vector: list[float]


class VectorIndexService:
    def __init__(self) -> None:
        self.items: dict[str, IndexItem] = {}
        self.ready = False

    def search_similar(
        self,
        vector: list[float],
        top_k: int,
        exclude_question_ids: list[str] | None = None,
    ) -> list[dict]:
        excluded = set(exclude_question_ids or [])
        results = []
        for item in self.items.values():
            if item.question_id in excluded:
                continue
            results.append(
                {
                    "questionId": item.question_id,
                    "stem": item.stem,
                    "similarity": cosine_similarity(vector, item.vector),
                    "topic": item.topic,
                    "questionType": item.question_type,
                }
            )
        return sorted(results, key=lambda item: item["similarity"], reverse=True)[:top_k]

    def add(self, item: IndexItem) -> None:
        self.items[item.question_id] = item
        self.ready = True

    def remove(self, question_id: str) -> None:
        self.items.pop(question_id, None)

    def clear(self) -> None:
        self.items.clear()
        self.ready = False


vector_index = VectorIndexService()


@lru_cache(maxsize=4)
def _build_embedding_service(
    provider: str,
    model_name: str,
    dimension: int,
) -> EmbeddingService:
    if provider == "real_e5":
        return E5EmbeddingService(model_name, dimension)
    return MockDeterministicEmbeddingService(dimension)


def get_embedding_service(settings: Settings) -> EmbeddingService:
    return _build_embedding_service(
        settings.embedding_provider,
        settings.embedding_model_name,
        settings.embedding_dimension,
    )


def embed_question(db: Session, question: Question, settings: Settings) -> QuestionEmbedding:
    service = get_embedding_service(settings)
    stem = QuestionTextBuilder.build_duplicate_search_text(question)
    normalized = TextNormalizer.normalize_for_comparison(stem)
    input_hash = hash_normalized_text(stem)
    model_info = service.get_model_info()
    existing = db.scalar(
        select(QuestionEmbedding).where(
            QuestionEmbedding.question_id == question.id,
            QuestionEmbedding.text_type == "stem",
            QuestionEmbedding.embedding_model == model_info["modelName"],
            QuestionEmbedding.input_text_hash == input_hash,
        )
    )
    if existing:
        record = existing
    else:
        vector = service.embed_text(E5InputFormatter.format_for_e5(stem))
        record = QuestionEmbedding(
            question_id=question.id,
            text_type="stem",
            embedding_model=model_info["modelName"],
            embedding_dimension=settings.embedding_dimension,
            input_text_hash=input_hash,
            normalized_text=normalized,
            vector=vector,
        )
        db.add(record)
        db.flush()
    vector_index.add(
        IndexItem(
            question_id=question.id,
            stem=question.stem,
            topic=question.topic,
            question_type=question.question_type,
            vector=record.vector,
        )
    )
    return record


def rebuild_index(db: Session, settings: Settings) -> dict:
    vector_index.clear()
    model_info = get_embedding_service(settings).get_model_info()
    db.execute(
        delete(QuestionEmbedding).where(
            QuestionEmbedding.embedding_model != model_info["modelName"]
        )
    )
    questions = list(
        db.scalars(
            select(Question).where(Question.status == QuestionStatus.APPROVED.value)
        )
    )
    embedded = 0
    failed = 0
    for question in questions:
        try:
            embed_question(db, question, settings)
            embedded += 1
        except Exception:
            failed += 1
    result = {
        "embeddedCount": embedded,
        "skippedCount": 0,
        "failedCount": failed,
        "modelName": model_info["modelName"],
        "provider": model_info["provider"],
        "dimension": settings.embedding_dimension,
    }
    db.add(
        AuditLog(
            entity_type="Embedding",
            entity_id="all",
            action="EMBEDDING_REINDEXED",
            actor="system",
            after_json=result,
        )
    )
    db.commit()
    return result


def embedding_status(db: Session, settings: Settings) -> dict:
    model_info = get_embedding_service(settings).get_model_info()
    count = (
        db.scalar(
            select(func.count())
            .select_from(QuestionEmbedding)
            .where(QuestionEmbedding.embedding_model == model_info["modelName"])
        )
        or 0
    )
    return {
        "modelName": model_info["modelName"],
        "provider": model_info["provider"],
        "dimension": settings.embedding_dimension,
        "questionEmbeddingCount": count,
        "indexReady": vector_index.ready,
    }
