from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.enums import GenerationProvider


@contextmanager
def generation_settings(
    client: TestClient,
    provider: GenerationProvider,
    api_key: str = "",
):
    settings = get_settings().model_copy(
        update={"generation_provider": provider, "generation_api_key": api_key}
    )
    client.app.dependency_overrides[get_settings] = lambda: settings
    try:
        yield settings
    finally:
        client.app.dependency_overrides.pop(get_settings, None)


class FakeDocumentQuestionGenerator:
    def __init__(self, settings) -> None:
        self.settings = settings

    def generate_questions(self, *, chunk_text: str, questions_per_chunk: int, target_language: str = "vi"):
        return [
            {
                "stem": "Mục tiêu chính của ưu tiên ABC trong chăm sóc cấp tính là gì?",
                "optionA": "Đảm bảo đánh giá đường thở, hô hấp và tuần hoàn",
                "optionB": "Giúp giảm thời gian ghi chép hồ sơ",
                "optionC": "Thay thế hoàn toàn đánh giá điều dưỡng",
                "optionD": "Giúp người bệnh tự chọn phác đồ điều trị",
                "correctAnswer": "A",
                "explanation": "Tài liệu nêu ABC ưu tiên Airway, Breathing và Circulation.",
                "difficulty": "medium",
                "topic": "Cấp cứu",
                "sourceExcerpt": "Airway - Breathing - Circulation giúp ưu tiên cấp cứu",
            }
        ][:questions_per_chunk]


class DuplicateDocumentQuestionGenerator(FakeDocumentQuestionGenerator):
    def generate_questions(self, *, chunk_text: str, questions_per_chunk: int, target_language: str = "vi"):
        return [
            {
                "stem": "Trong chăm sóc cấp tính, ưu tiên ABC để làm gì?",
                "optionA": "A",
                "optionB": "B",
                "optionC": "C",
                "optionD": "D",
                "correctAnswer": "A",
                "explanation": "Dựa trên đoạn tài liệu.",
                "difficulty": "medium",
                "topic": "Cấp cứu",
                "sourceExcerpt": "Airway - Breathing - Circulation giúp ưu tiên cấp cứu",
            }
        ]


def upload_text_document(client: TestClient) -> dict:
    content = (
        "Airway - Breathing - Circulation giúp ưu tiên cấp cứu. "
        "Điều dưỡng cần đánh giá đường thở, hô hấp và tuần hoàn trước. "
    ) * 12
    response = client.post(
        "/documents",
        files={"file": ("abc.txt", content.encode("utf-8"), "text/plain")},
    )

    assert response.status_code == 201
    return response.json()["data"]


def test_markdown_document_upload_is_treated_as_text(client: TestClient) -> None:
    content = "# Tai lieu mau\n\nAirway - Breathing - Circulation giup uu tien cap cuu. " * 10
    response = client.post(
        "/documents",
        files={"file": ("sample.md", content.encode("utf-8"), "text/markdown")},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "READY"
    assert data["chunkCount"] >= 1


def test_document_generation_uses_mock_provider_without_api_key(client: TestClient) -> None:
    document = upload_text_document(client)
    response = client.post(
        f"/documents/{document['id']}/question-jobs",
        json={"questionsPerChunk": 1},
    )

    assert response.status_code == 201
    job = response.json()["data"]
    assert job["provider"] == "mock"
    assert job["model"] == "mock-document-generator"
    assert job["status"] == "GENERATED"
    assert job["candidateCount"] >= 1
    assert job["candidates"][0]["sourceExcerpt"]


def test_document_upload_pages_render_and_create_question_candidates(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.documents.service.DeepSeekDocumentQuestionGenerator",
        FakeDocumentQuestionGenerator,
    )
    with generation_settings(client, GenerationProvider.api, api_key="test-key"):
        document = upload_text_document(client)
        assert document["status"] == "READY"
        assert document["chunkCount"] >= 1
        assert client.get("/documents", headers={"Accept": "text/html"}).status_code == 200
        detail_page = client.get(f"/documents/{document['id']}", headers={"Accept": "text/html"})
        assert "Tạo câu hỏi từ tài liệu" in detail_page.text

        before_count = client.get("/embeddings/status").json()["data"]["questionEmbeddingCount"]
        job_response = client.post(
            f"/documents/{document['id']}/question-jobs",
            json={"questionsPerChunk": 1},
        )

        assert job_response.status_code == 201
        job = job_response.json()["data"]
        assert job["status"] == "GENERATED"
        assert job["candidateCount"] >= 1
        candidate = job["candidates"][0]
        assert candidate["label"] in {"GOOD", "NEED_REVIEW"}

        job_page = client.get(
            f"/document-question-jobs/{job['id']}",
            headers={"Accept": "text/html"},
        )
        assert "Duyệt câu hỏi từ tài liệu" in job_page.text

        assert client.post(
            f"/document-question-candidates/{candidate['id']}/approve",
            json={"reviewerNotes": "Đã kiểm tra nguồn."},
        ).status_code == 200
        saved = client.post(
            f"/document-question-candidates/{candidate['id']}/save-as-question"
        ).json()["data"]
        assert saved["status"] == "SAVED"
        question = client.get(
            f"/questions/{saved['newQuestionId']}",
            headers={"Accept": "application/json"},
        ).json()["data"]
        assert question["questionType"] == "ORIGINAL"
        assert document["id"] in question["sourceDocument"]
        after_count = client.get("/embeddings/status").json()["data"]["questionEmbeddingCount"]
        assert after_count == before_count + 1


def test_document_generation_marks_semantic_duplicates_for_review(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.documents.service.DeepSeekDocumentQuestionGenerator",
        DuplicateDocumentQuestionGenerator,
    )
    with generation_settings(client, GenerationProvider.api, api_key="test-key"):
        document = upload_text_document(client)
        response = client.post(
            f"/documents/{document['id']}/question-jobs",
            json={"questionsPerChunk": 1},
        )

    assert response.status_code == 201
    candidate = response.json()["data"]["candidates"][0]
    assert candidate["label"] == "NEED_REVIEW"
    assert candidate["duplicateQuestionId"] == "Q001"
    assert "STRONG_DUPLICATE_WITH_EXISTING_QUESTION" in candidate["warnings"]


def test_document_generation_without_api_key_persists_failed_job(client: TestClient) -> None:
    with generation_settings(client, GenerationProvider.api, api_key=""):
        document = upload_text_document(client)

        response = client.post(
            f"/documents/{document['id']}/question-jobs",
            json={"questionsPerChunk": 1},
        )

    assert response.status_code == 503
    job_id = response.json()["error"]["details"]["jobId"]
    failed = client.get(
        f"/document-question-jobs/{job_id}",
        headers={"Accept": "application/json"},
    ).json()["data"]
    assert failed["status"] == "FAILED"
    assert failed["candidates"] == []
