from contextlib import contextmanager
from io import BytesIO

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.enums import GenerationProvider
from app.modules.documents.providers import (
    DocumentGenerationUsage,
    DocumentQuestionBatch,
    DocumentQuestionValidation,
)


@contextmanager
def generation_settings(
    client: TestClient,
    provider: GenerationProvider,
    api_key: str = "",
    **overrides,
):
    settings = get_settings().model_copy(
        update={"generation_provider": provider, "generation_api_key": api_key, **overrides}
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
        questions = [
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
        return DocumentQuestionBatch(
            questions=questions,
            model="deepseek-v4-flash",
            prompt_version="docgen-mvp-flash-v1",
            knowledge_points=[
                {
                    "id": "KP1",
                    "statement": "ABC giúp ưu tiên cấp cứu.",
                    "type": "principle",
                    "importance": "high",
                    "sourceExcerpt": "Airway - Breathing - Circulation giúp ưu tiên cấp cứu",
                }
            ],
            usage=DocumentGenerationUsage(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                latency_ms=250,
                call_count=2,
            ),
        )


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


class InvalidOptionDocumentQuestionGenerator(FakeDocumentQuestionGenerator):
    def generate_questions(self, *, chunk_text: str, questions_per_chunk: int, target_language: str = "vi"):
        return [
            {
                "stem": "Theo tài liệu, nhận định nào đúng về ABC?",
                "optionA": "Tất cả đều đúng",
                "optionB": "Tất cả đều đúng",
                "optionC": "ABC không liên quan cấp cứu",
                "optionD": "Không có đáp án nào",
                "correctAnswer": "A",
                "explanation": "Dựa trên đoạn tài liệu.",
                "difficulty": "medium",
                "topic": "Cấp cứu",
                "sourceExcerpt": "Airway - Breathing - Circulation giúp ưu tiên cấp cứu",
            }
        ]


class FailsFirstChunkThenSucceedsGenerator(FakeDocumentQuestionGenerator):
    failed_once = False

    def generate_questions(self, *, chunk_text: str, questions_per_chunk: int, target_language: str = "vi"):
        if "FIRST_CHUNK_FAIL" in chunk_text and not self.__class__.failed_once:
            self.__class__.failed_once = True
            raise RuntimeError("temporary chunk failure")
        return super().generate_questions(
            chunk_text=chunk_text,
            questions_per_chunk=questions_per_chunk,
            target_language=target_language,
        )


class CountingDocumentQuestionGenerator(FakeDocumentQuestionGenerator):
    call_count = 0

    def generate_questions(self, *, chunk_text: str, questions_per_chunk: int, target_language: str = "vi"):
        self.__class__.call_count += 1
        return super().generate_questions(
            chunk_text=chunk_text,
            questions_per_chunk=questions_per_chunk,
            target_language=target_language,
        )


class LlmRejectsQuestionGenerator(FakeDocumentQuestionGenerator):
    def validate_question(self, *, chunk_text: str, question: dict, target_language: str = "vi"):
        return DocumentQuestionValidation(
            result={
                "answerable": False,
                "singleBestAnswer": False,
                "correctAnswerSupported": False,
                "qualityScore": 0.31,
                "issues": ["NOT_ANSWERABLE", "MULTIPLE_VALID_OPTIONS"],
                "rationale": "Không đủ dữ kiện từ nguồn và có nhiều đáp án dễ đúng.",
            },
            model="deepseek-v4-flash",
            prompt_version="docgen-mvp-flash-v1",
            usage=DocumentGenerationUsage(
                prompt_tokens=20,
                completion_tokens=10,
                total_tokens=30,
                latency_ms=50,
                call_count=1,
            ),
        )


def upload_text_document(client: TestClient) -> dict:
    content = (
        "Airway - Breathing - Circulation giúp ưu tiên cấp cứu. "
        "Điều dưỡng cần đánh giá đường thở, hô hấp và tuần hoàn trước. "
    ) * 70
    response = client.post(
        "/documents",
        files={"file": ("abc.txt", content.encode("utf-8"), "text/plain")},
    )

    assert response.status_code == 201
    return response.json()["data"]


def upload_two_chunk_document(client: TestClient) -> dict:
    first = (
        "FIRST_CHUNK_FAIL Airway - Breathing - Circulation giúp ưu tiên cấp cứu. "
        "Điều dưỡng cần đánh giá đường thở, hô hấp và tuần hoàn trước. "
    ) * 70
    second = (
        "SECOND_CHUNK_OK Suy hô hấp cần được phát hiện sớm. "
        "Điều dưỡng theo dõi SpO2 và biểu hiện khó thở của người bệnh. "
    ) * 12
    content = first + "\n\n" + second
    response = client.post(
        "/documents",
        files={"file": ("two-chunks.txt", content.encode("utf-8"), "text/plain")},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["chunkCount"] >= 2
    return data


def make_docx_bytes(text: str) -> bytes:
    from docx import Document as DocxDocument

    document = DocxDocument()
    for paragraph in text.split("\n\n"):
        document.add_paragraph(paragraph)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def make_text_pdf_bytes(text: str) -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 50 780 Td ({text}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_blank_pdf_bytes() -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


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


def test_pdf_text_and_docx_upload_create_chunks(client: TestClient) -> None:
    pdf_response = client.post(
        "/documents",
        files={
            "file": (
                "abc.pdf",
                make_text_pdf_bytes("Airway Breathing Circulation helps emergency prioritization."),
                "application/pdf",
            )
        },
    )
    docx_response = client.post(
        "/documents",
        files={
            "file": (
                "abc.docx",
                make_docx_bytes(
                    "Chương 1 Cấp cứu\n\n"
                    "Airway - Breathing - Circulation giúp ưu tiên cấp cứu."
                ),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert pdf_response.status_code == 201
    assert pdf_response.json()["data"]["status"] == "READY"
    assert pdf_response.json()["data"]["chunkCount"] >= 1
    assert docx_response.status_code == 201
    assert docx_response.json()["data"]["status"] == "READY"
    assert docx_response.json()["data"]["sections"]


def test_blank_pdf_is_marked_ocr_required(client: TestClient) -> None:
    response = client.post(
        "/documents",
        files={"file": ("scan-like.pdf", make_blank_pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "OCR_REQUIRED"
    assert data["chunkCount"] == 0
    assert "OCR" in data["errorMessage"]


def test_document_upload_persists_section_tree_and_chunk_metadata(client: TestClient) -> None:
    content = (
        "Chương 1 Cấp cứu ban đầu\n\n"
        "Airway - Breathing - Circulation giúp ưu tiên cấp cứu. "
        "Điều dưỡng cần đánh giá đường thở, hô hấp và tuần hoàn trước.\n\n"
        "1.1 Theo dõi hô hấp\n\n"
        "Điều dưỡng theo dõi SpO2 và biểu hiện khó thở của người bệnh. "
    ) * 20

    response = client.post(
        "/documents",
        files={"file": ("structured.txt", content.encode("utf-8"), "text/plain")},
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["sections"]
    assert data["sections"][0]["title"].startswith("Chương 1")
    assert data["chunks"]
    assert data["chunks"][0]["chunkType"] == "generation"
    assert data["chunks"][0]["tokenCount"] > 0
    assert data["chunks"][0]["sectionPath"]
    if len(data["chunks"]) > 1:
        assert data["chunks"][0]["nextChunkId"] == data["chunks"][1]["id"]
        assert data["chunks"][1]["previousChunkId"] == data["chunks"][0]["id"]


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
    with generation_settings(
        client,
        GenerationProvider.api,
        api_key="test-key",
        generation_prompt_usd_per_1m_tokens=1.0,
        generation_completion_usd_per_1m_tokens=2.0,
    ):
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
        assert job["model"] == "deepseek-v4-flash"
        assert job["promptVersion"] == "docgen-mvp-flash-v1"
        assert job["llmCallCount"] >= 2
        assert job["totalTokens"] >= 150
        assert job["estimatedCostUsd"] == 0.0002
        assert job["knowledgePoints"]
        assert job["knowledgePoints"][0]["chunkId"]
        candidate = job["candidates"][0]
        assert candidate["label"] in {"GOOD", "NEED_REVIEW"}
        assert candidate["sourcePageStart"] is not None
        assert candidate["sourceSectionPath"]

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


def test_document_generation_rejects_duplicate_or_all_of_above_options(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.documents.service.DeepSeekDocumentQuestionGenerator",
        InvalidOptionDocumentQuestionGenerator,
    )
    with generation_settings(client, GenerationProvider.api, api_key="test-key"):
        document = upload_text_document(client)
        response = client.post(
            f"/documents/{document['id']}/question-jobs",
            json={"questionsPerChunk": 1},
        )

    assert response.status_code == 201
    candidate = response.json()["data"]["candidates"][0]
    assert candidate["label"] == "REJECTED"
    assert "DOCUMENT_OPTION_DUPLICATE" in candidate["warnings"]
    assert "DOCUMENT_OPTION_INVALID_PATTERN" in candidate["warnings"]


def test_document_generation_rejects_llm_invalid_question(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.documents.service.DeepSeekDocumentQuestionGenerator",
        LlmRejectsQuestionGenerator,
    )
    with generation_settings(client, GenerationProvider.api, api_key="test-key"):
        document = upload_text_document(client)
        response = client.post(
            f"/documents/{document['id']}/question-jobs",
            json={"questionsPerChunk": 1},
        )

    assert response.status_code == 201
    job = response.json()["data"]
    candidate = job["candidates"][0]
    assert job["llmCallCount"] >= 3
    assert candidate["label"] == "REJECTED"
    assert candidate["qualityScore"] == 0.31
    assert candidate["llmValidation"]["rationale"]
    assert "DOCUMENT_LLM_NOT_ANSWERABLE" in candidate["warnings"]
    assert "DOCUMENT_LLM_MULTIPLE_ANSWERS" in candidate["warnings"]
    assert "DOCUMENT_LLM_CORRECT_ANSWER_UNSUPPORTED" in candidate["warnings"]
    assert "DOCUMENT_LLM_LOW_QUALITY" in candidate["warnings"]


def test_document_generation_partial_failure_can_retry_failed_chunks(
    client: TestClient,
    monkeypatch,
) -> None:
    FailsFirstChunkThenSucceedsGenerator.failed_once = False
    monkeypatch.setattr(
        "app.modules.documents.service.DeepSeekDocumentQuestionGenerator",
        FailsFirstChunkThenSucceedsGenerator,
    )
    with generation_settings(client, GenerationProvider.api, api_key="test-key"):
        document = upload_two_chunk_document(client)
        response = client.post(
            f"/documents/{document['id']}/question-jobs",
            json={"questionsPerChunk": 1},
        )

        assert response.status_code == 201
        job = response.json()["data"]
        assert job["status"] == "PARTIALLY_COMPLETED"
        assert job["failedChunkCount"] == 1
        assert job["chunkErrors"][0]["code"] == "RuntimeError"
        assert job["candidateCount"] >= 1

        retry = client.post(
            f"/document-question-jobs/{job['id']}/retry-failed-chunks"
        )

    assert retry.status_code == 200
    retried = retry.json()["data"]
    assert retried["status"] == "GENERATED"
    assert retried["failedChunkCount"] == 0
    assert retried["chunkErrors"] == []
    assert retried["candidateCount"] >= job["candidateCount"] + 1


def test_document_generation_reuses_cached_candidates_for_same_chunk_request(
    client: TestClient,
    monkeypatch,
) -> None:
    CountingDocumentQuestionGenerator.call_count = 0
    monkeypatch.setattr(
        "app.modules.documents.service.DeepSeekDocumentQuestionGenerator",
        CountingDocumentQuestionGenerator,
    )
    with generation_settings(client, GenerationProvider.api, api_key="test-key"):
        document = upload_text_document(client)
        first = client.post(
            f"/documents/{document['id']}/question-jobs",
            json={"questionsPerChunk": 1},
        ).json()["data"]
        calls_after_first = CountingDocumentQuestionGenerator.call_count
        second = client.post(
            f"/documents/{document['id']}/question-jobs",
            json={"questionsPerChunk": 1},
        ).json()["data"]

    assert first["status"] == "GENERATED"
    assert second["status"] == "GENERATED"
    assert second["candidateCount"] == first["candidateCount"]
    assert CountingDocumentQuestionGenerator.call_count == calls_after_first
    assert second["llmCallCount"] == 0
    assert all(candidate["generationKey"] for candidate in second["candidates"])


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
