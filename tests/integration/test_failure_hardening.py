from fastapi.testclient import TestClient

from app.core.enums import ErrorCode
from app.core.errors import AppError
from app.modules.embeddings.vector_index import vector_index


def create_job(client: TestClient) -> dict:
    response = client.post(
        "/paraphrase-jobs",
        json={"sourceQuestionId": "Q001", "requestedCount": 3, "provider": "mock"},
    )
    return response.json()["data"]


def test_paraphrase_validation_does_not_require_vector_index(client: TestClient) -> None:
    job = create_job(client)
    vector_index.clear()
    response = client.post(f"/paraphrase-jobs/{job['jobId']}/validate")
    detail = client.get(
        f"/paraphrase-jobs/{job['jobId']}", headers={"Accept": "application/json"}
    ).json()["data"]
    assert response.status_code == 200
    assert all(
        "VECTOR_INDEX_NOT_READY" not in item["warnings"]
        for item in detail["candidates"]
    )


def test_exam_question_addition_stops_when_duplicate_index_is_not_ready(
    client: TestClient,
) -> None:
    exam = client.post("/exams", json={"title": "Đề kiểm thử"}).json()["data"]
    assert client.post(
        f"/exams/{exam['id']}/questions", json={"questionId": "Q001"}
    ).status_code == 201
    vector_index.clear()
    response = client.post(
        f"/exams/{exam['id']}/questions",
        json={"questionId": "Q002"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "VECTOR_INDEX_FAILED"


def test_embedding_failure_keeps_candidate_generated(client: TestClient, monkeypatch) -> None:
    job = create_job(client)
    candidate = client.get(
        f"/paraphrase-jobs/{job['jobId']}", headers={"Accept": "application/json"}
    ).json()["data"]["candidates"][0]

    class FailingEmbeddingService:
        def embed_texts(self, texts):
            raise AppError(
                ErrorCode.EMBEDDING_FAILED,
                "Embedding unavailable",
                status_code=503,
            )

    monkeypatch.setattr(
        "app.modules.validation.service.get_embedding_service",
        lambda settings: FailingEmbeddingService(),
    )
    response = client.post(f"/paraphrase-candidates/{candidate['id']}/validate")
    unchanged = client.get(f"/paraphrase-candidates/{candidate['id']}").json()["data"]
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EMBEDDING_FAILED"
    assert unchanged["status"] == "GENERATED"
    assert unchanged["semanticSimilarityToSource"] is None
