"""Lazy sentence-transformers implementation for multilingual E5."""

from app.core.enums import ErrorCode
from app.core.errors import AppError


class E5EmbeddingService:
    def __init__(self, model_name: str, dimension: int = 384) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
            except Exception as exc:
                raise AppError(
                    ErrorCode.EMBEDDING_FAILED,
                    "Không thể tải mô hình embedding E5",
                    status_code=503,
                    details={"reason": str(exc)},
                ) from exc
        return self._model

    def embed_text(self, text: str) -> list[float]:
        try:
            vector = self._load_model().encode(
                text, normalize_embeddings=True, convert_to_numpy=True
            )
            result = vector.tolist()
            if len(result) != self.dimension:
                raise ValueError(f"Expected dimension {self.dimension}, got {len(result)}")
            return result
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                ErrorCode.EMBEDDING_FAILED,
                "Không thể tạo embedding",
                status_code=503,
                details={"reason": str(exc)},
            ) from exc

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        try:
            vectors = self._load_model().encode(
                texts,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
            results = vectors.tolist()
            if any(len(vector) != self.dimension for vector in results):
                raise ValueError(f"Expected embedding dimension {self.dimension}")
            return results
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                ErrorCode.EMBEDDING_FAILED,
                "Không thể tạo embedding",
                status_code=503,
                details={"reason": str(exc)},
            ) from exc

    def get_model_info(self) -> dict:
        return {
            "modelName": self.model_name,
            "dimension": self.dimension,
            "provider": "real_e5",
        }
