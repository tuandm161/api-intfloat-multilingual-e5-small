from app.core.config import Settings
from app.core.enums import GenerationProvider


def test_settings_can_be_overridden_by_environment(monkeypatch) -> None:
    monkeypatch.setenv("VECTOR_TOP_K", "7")
    monkeypatch.setenv("GENERATION_PROVIDER", "local")

    settings = Settings(_env_file=None)

    assert settings.vector_top_k == 7
    assert settings.generation_provider is GenerationProvider.local


def test_public_config_has_an_explicit_allowlist() -> None:
    settings = Settings(generation_api_key="top-secret", _env_file=None)

    assert settings.public_config() == {
        "generationProvider": "mock",
        "embeddingModelName": "intfloat/multilingual-e5-small",
        "embeddingProvider": "mock_deterministic",
        "embeddingDimension": 384,
        "vectorTopK": 10,
    }
