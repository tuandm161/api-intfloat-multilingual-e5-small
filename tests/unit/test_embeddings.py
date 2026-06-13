from app.modules.embeddings.interfaces import cosine_similarity
from app.modules.embeddings.mock_service import MockDeterministicEmbeddingService


def test_mock_embedding_has_expected_dimension_and_is_deterministic() -> None:
    service = MockDeterministicEmbeddingService(384)
    first = service.embed_text("query: chăm sóc ABC")
    second = service.embed_text("query: chăm sóc ABC")
    assert len(first) == 384
    assert first == second
    assert cosine_similarity(first, second) == 1.0
