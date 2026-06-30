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

    paraphrase_provider: GenerationProvider = GenerationProvider.local
    local_paraphrase_engine: str = "qwen"
    local_paraphrase_model_repo_id: str = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
    local_paraphrase_model_filename: str = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
    local_paraphrase_context_tokens: int = Field(default=2048, ge=512, le=8192)
    local_paraphrase_max_tokens: int = Field(default=1024, ge=64, le=2048)
    local_paraphrase_temperature: float = Field(default=0.2, ge=0, le=2)
    local_paraphrase_top_p: float = Field(default=0.9, gt=0, le=1)
    local_paraphrase_repeat_penalty: float = Field(default=1.05, ge=1, le=2)
    local_paraphrase_threads: int = Field(default=0, ge=0)
    local_paraphrase_gpu_layers: int = Field(default=0, ge=0)
    vietquill_model_repo_id: str = "ngwgsang/vietquill-vit5-base-tsubaki"
    vietquill_device: str = "cpu"
    vietquill_style: str = "balanced"
    vietquill_num_beams: int = Field(default=6, ge=1, le=20)
    vietquill_max_length: int = Field(default=128, ge=32, le=512)

    generation_provider: GenerationProvider = GenerationProvider.mock
    generation_api_key: str = ""
    generation_api_base_url: str = "https://api.deepseek.com"
    generation_model: str = "deepseek-v4-flash"
    generation_fallback_model: str = "deepseek-v4-pro"
    generation_timeout_seconds: float = Field(default=60.0, gt=0)
    generation_max_retries: int = Field(default=1, ge=0, le=5)
    generation_prompt_usd_per_1m_tokens: float = Field(default=0.0, ge=0)
    generation_completion_usd_per_1m_tokens: float = Field(default=0.0, ge=0)

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
    validation_lexical_too_different_min: float = Field(default=0.25, ge=0, le=1)

    def public_config(self) -> dict[str, str | int]:
        """Return only values that are safe to expose to the browser."""
        return {
            "paraphraseProvider": self.paraphrase_provider.value,
            "generationProvider": self.generation_provider.value,
            "embeddingModelName": self.embedding_model_name,
            "embeddingProvider": self.embedding_provider,
            "embeddingDimension": self.embedding_dimension,
            "vectorTopK": self.vector_top_k,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
