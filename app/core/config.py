"""Environment-backed application configuration."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import GenerationProvider


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = "sqlite:///./question_paraphrase.db"

    generation_provider: GenerationProvider = GenerationProvider.mock
    generation_api_key: str = ""
    generation_api_base_url: str = "https://api.deepseek.com"
    generation_model: str = "deepseek-v4-flash"
    generation_fallback_model: str = "deepseek-v4-pro"
    generation_timeout_seconds: float = Field(default=60.0, gt=0)
    generation_max_retries: int = Field(default=1, ge=0, le=5)

    embedding_model_name: str = "intfloat/multilingual-e5-small"
    embedding_provider: str = "real_e5"
    embedding_dimension: int = Field(default=384, gt=0)
    vector_index_type: str = "local"
    vector_top_k: int = Field(default=10, gt=0)

    document_chunk_target_chars: int = Field(default=7000, ge=1000)
    document_chunk_max_chars: int = Field(default=10000, ge=1000)
    document_chunk_overlap_chars: int = Field(default=800, ge=0)
    document_questions_per_chunk: int = Field(default=3, ge=1, le=5)

    validation_semantic_pass_min: float = Field(default=0.86, ge=0, le=1)
    validation_semantic_review_min: float = Field(default=0.78, ge=0, le=1)
    validation_duplicate_strong_min: float = Field(default=0.88, ge=0, le=1)
    validation_duplicate_review_min: float = Field(default=0.80, ge=0, le=1)
    validation_duplicate_real_e5_min: float = Field(default=0.93, ge=0, le=1)
    validation_lexical_too_similar_max: float = Field(default=0.85, ge=0, le=1)
    validation_lexical_too_different_min: float = Field(default=0.15, ge=0, le=1)

    def public_config(self) -> dict[str, str | int]:
        """Return only values that are safe to expose to the browser."""
        return {
            "generationProvider": self.generation_provider.value,
            "embeddingModelName": self.embedding_model_name,
            "embeddingProvider": self.embedding_provider,
            "embeddingDimension": self.embedding_dimension,
            "vectorTopK": self.vector_top_k,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
