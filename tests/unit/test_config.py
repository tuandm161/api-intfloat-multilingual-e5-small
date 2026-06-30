from app.core.config import Settings
from app.core.enums import GenerationProvider


def test_settings_can_be_overridden_by_environment(monkeypatch) -> None:
    monkeypatch.setenv("VECTOR_TOP_K", "7")
    monkeypatch.setenv("GENERATION_PROVIDER", "local")
    monkeypatch.setenv("PARAPHRASE_PROVIDER", "mock")
    monkeypatch.setenv("LOCAL_PARAPHRASE_CONTEXT_TOKENS", "4096")
    monkeypatch.setenv("LOCAL_PARAPHRASE_THREADS", "4")

    settings = Settings(_env_file=None)

    assert settings.vector_top_k == 7
    assert settings.generation_provider is GenerationProvider.local
    assert settings.paraphrase_provider is GenerationProvider.mock
    assert settings.local_paraphrase_context_tokens == 4096
    assert settings.local_paraphrase_threads == 4


def test_public_config_has_an_explicit_allowlist() -> None:
    settings = Settings(generation_api_key="top-secret", _env_file=None)

    assert settings.public_config() == {
        "paraphraseProvider": "local",
        "generationProvider": "mock",
        "embeddingModelName": "intfloat/multilingual-e5-small",
        "embeddingProvider": "mock_deterministic",
        "embeddingDimension": 384,
        "vectorTopK": 10,
    }
