from app.modules.documents.extractors import ExtractedPage
from app.modules.documents.processing import build_section_tree, clean_pages, split_into_chunks
from app.modules.documents.providers import (
    DeepSeekDocumentQuestionGenerator,
    DocumentGenerationUsage,
    DocumentQuestionBatch,
    DocumentQuestionValidation,
)
from app.modules.paraphrase.providers.api import ApiParaphraseGenerator
from app.core.config import Settings


def test_clean_pages_and_split_chunks_preserve_metadata_and_overlap() -> None:
    pages = clean_pages(
        [
            ExtractedPage(
                1,
                "Giáo trình ABC\n\nAirway - Breathing - Circulation giúp ưu tiên cấp cứu. " * 20,
            ),
            ExtractedPage(
                2,
                "Breathing cần được đánh giá để phát hiện suy hô hấp. " * 20,
            ),
        ]
    )

    chunks = split_into_chunks(pages, target_chars=450, max_chars=650, overlap_chars=80)

    assert len(chunks) >= 2
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 2
    assert chunks[0].text[-40:] in chunks[1].text


def test_clean_pages_remove_noise_and_chunks_keep_numbered_section_title() -> None:
    pages = clean_pages(
        [
            ExtractedPage(
                1,
                "\n".join(
                    [
                        "Mục lục ........................................ 1",
                        "1",
                        "1.1 Đánh giá ban đầu",
                        "",
                        "Airway - Breathing - Circulation giúp ưu tiên cấp cứu.",
                        "Điều dưỡng cần đánh giá đường thở, hô hấp và tuần hoàn.",
                    ]
                ),
            )
        ]
    )

    assert "Mục lục" not in pages[0].text
    assert "\n1\n" not in f"\n{pages[0].text}\n"

    chunks = split_into_chunks(pages, target_chars=160, max_chars=260, overlap_chars=80)

    assert chunks
    assert chunks[0].section_title == "1.1 Đánh giá ban đầu"
    assert chunks[0].section_path == "1.1 Đánh giá ban đầu"
    assert chunks[0].token_count > 0
    assert "Airway - Breathing - Circulation" in chunks[0].text


def test_build_section_tree_preserves_heading_hierarchy() -> None:
    pages = clean_pages(
        [
            ExtractedPage(
                1,
                "\n\n".join(
                    [
                        "Chương 1 Cấp cứu ban đầu",
                        "ABC giúp ưu tiên cấp cứu.",
                        "1.1 Đánh giá đường thở",
                        "Đường thở cần được đánh giá đầu tiên.",
                    ]
                ),
            )
        ]
    )

    sections = build_section_tree(pages)

    assert [section.title for section in sections] == [
        "Chương 1 Cấp cứu ban đầu",
        "1.1 Đánh giá đường thở",
    ]
    assert sections[1].parent_index == sections[0].section_index
    assert sections[1].path == "Chương 1 Cấp cứu ban đầu > 1.1 Đánh giá đường thở"


def test_api_paraphrase_response_parser_accepts_json_candidates() -> None:
    stems = ApiParaphraseGenerator._parse_stems(
        {"candidates": [{"stem": "Câu hỏi đã được viết lại là gì?"}]},
        3,
    )

    assert stems == ["Câu hỏi đã được viết lại là gì?"]


class FakeDeepSeekDocumentQuestionGenerator(DeepSeekDocumentQuestionGenerator):
    def __init__(self) -> None:
        super().__init__(Settings(_env_file=None, generation_api_key="test-key"))
        self.calls = []

    def _call_with_fallback(self, payload):
        self.calls.append(payload["task"])
        usage = DocumentGenerationUsage(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            latency_ms=7,
            call_count=1,
        )
        if payload["task"] == "knowledge_extraction":
            return (
                {
                    "knowledgePoints": [
                        {
                            "id": "KP1",
                            "statement": "ABC giúp ưu tiên cấp cứu.",
                            "type": "principle",
                            "importance": "high",
                            "sourceExcerpt": "ABC giúp ưu tiên cấp cứu.",
                        }
                    ]
                },
                usage,
                "deepseek-v4-flash",
            )
        if payload["task"] == "question_generation":
            return (
                {
                    "questions": [
                        {
                            "stem": "Mục tiêu của ABC trong cấp cứu là gì?",
                            "optionA": "Ưu tiên đánh giá đường thở, hô hấp và tuần hoàn.",
                            "optionB": "Thay thế đánh giá ban đầu.",
                            "optionC": "Giảm việc ghi hồ sơ.",
                            "optionD": "Chọn khoa điều trị ngẫu nhiên.",
                            "correctAnswer": "A",
                            "explanation": "ABC giúp ưu tiên cấp cứu.",
                            "difficulty": "medium",
                            "topic": "ABC",
                            "sourceExcerpt": "ABC giúp ưu tiên cấp cứu.",
                            "knowledgePointId": "KP1",
                        }
                    ]
                },
                usage,
                "deepseek-v4-flash",
            )
        return (
            {
                "answerable": True,
                "singleBestAnswer": True,
                "correctAnswerSupported": True,
                "qualityScore": 0.91,
                "issues": [],
                "rationale": "Câu hỏi bám nguồn.",
            },
            usage,
            "deepseek-v4-flash",
        )


def test_deepseek_document_generator_extracts_knowledge_then_questions() -> None:
    generator = FakeDeepSeekDocumentQuestionGenerator()

    batch = generator.generate_questions(
        chunk_text="ABC giúp ưu tiên cấp cứu. Điều dưỡng đánh giá đường thở trước.",
        questions_per_chunk=1,
    )

    assert isinstance(batch, DocumentQuestionBatch)
    assert generator.calls == ["knowledge_extraction", "question_generation"]
    assert batch.questions[0]["knowledgePointId"] == "KP1"
    assert batch.knowledge_points[0]["id"] == "KP1"
    assert batch.model == "deepseek-v4-flash"
    assert batch.usage.call_count == 2
    assert batch.usage.total_tokens == 30


def test_deepseek_document_generator_validates_question_candidate() -> None:
    generator = FakeDeepSeekDocumentQuestionGenerator()

    validation = generator.validate_question(
        chunk_text="ABC giúp ưu tiên cấp cứu.",
        question={
            "stem": "Mục tiêu của ABC là gì?",
            "optionA": "Ưu tiên cấp cứu.",
            "optionB": "Giảm hồ sơ.",
            "optionC": "Chọn khoa ngẫu nhiên.",
            "optionD": "Thay đánh giá ban đầu.",
            "correctAnswer": "A",
        },
    )

    assert isinstance(validation, DocumentQuestionValidation)
    assert generator.calls == ["question_validation"]
    assert validation.result["qualityScore"] == 0.91
    assert validation.usage.call_count == 1
