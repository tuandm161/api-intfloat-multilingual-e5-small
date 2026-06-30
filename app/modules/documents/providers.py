"""Question generation providers for document chunks."""

from dataclasses import dataclass, field
import json
import re
import time
from typing import Any

import httpx

from app.core.config import Settings
from app.core.enums import ErrorCode
from app.core.errors import AppError

DOCUMENT_GENERATION_PROMPT_VERSION = "docgen-mvp-flash-v1"


@dataclass
class DocumentGenerationUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    call_count: int = 0

    def add(self, other: "DocumentGenerationUsage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        self.latency_ms += other.latency_ms
        self.call_count += other.call_count


@dataclass
class DocumentQuestionBatch:
    questions: list[dict[str, Any]]
    model: str
    prompt_version: str = DOCUMENT_GENERATION_PROMPT_VERSION
    usage: DocumentGenerationUsage = field(default_factory=DocumentGenerationUsage)
    knowledge_points: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DocumentQuestionValidation:
    result: dict[str, Any]
    model: str
    prompt_version: str = DOCUMENT_GENERATION_PROMPT_VERSION
    usage: DocumentGenerationUsage = field(default_factory=DocumentGenerationUsage)


class MockDocumentQuestionGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_questions(
        self,
        *,
        chunk_text: str,
        questions_per_chunk: int,
        target_language: str = "vi",
    ) -> DocumentQuestionBatch:
        excerpt = self._source_excerpt(chunk_text)
        topic = self._topic(excerpt)
        knowledge_points = [
            {
                "id": "KP1",
                "statement": topic,
                "type": "fact",
                "importance": "medium",
                "sourceExcerpt": excerpt,
                "generationEligible": True,
            }
        ]
        templates = [
            (
                f"Theo tài liệu, nhận định nào đúng nhất về nội dung: {topic}?",
                "Nội dung này được nêu hoặc suy ra trực tiếp từ đoạn tài liệu.",
            ),
            (
                f"Ý chính của đoạn tài liệu liên quan đến {topic} là gì?",
                "Đoạn tài liệu cung cấp thông tin nền để trả lời câu hỏi này.",
            ),
            (
                f"Khi đọc đoạn tài liệu về {topic}, lựa chọn nào phù hợp nhất?",
                "Lựa chọn đúng bám sát thông tin trong trích đoạn nguồn.",
            ),
            (
                f"Câu nào phản ánh đúng thông tin trong đoạn tài liệu về {topic}?",
                "Câu trả lời đúng không dùng kiến thức ngoài tài liệu.",
            ),
            (
                f"Điểm cần ghi nhớ từ đoạn tài liệu về {topic} là gì?",
                "Câu hỏi được tạo từ trích đoạn tài liệu đã upload.",
            ),
        ]
        questions = []
        for stem, explanation in templates[:questions_per_chunk]:
            questions.append(
                {
                    "stem": stem,
                    "optionA": explanation,
                    "optionB": "Thông tin này không xuất hiện trong đoạn tài liệu.",
                    "optionC": "Đoạn tài liệu khẳng định điều ngược lại.",
                    "optionD": "Không đủ dữ kiện để thay thế đáp án đúng.",
                    "correctAnswer": "A",
                    "explanation": explanation,
                    "difficulty": "medium",
                    "topic": topic,
                    "sourceExcerpt": excerpt,
                }
            )
        return DocumentQuestionBatch(
            questions=questions,
            model="mock-document-generator",
            prompt_version="mock-document-generator-v1",
            knowledge_points=knowledge_points,
        )

    def validate_question(
        self,
        *,
        chunk_text: str,
        question: dict[str, Any],
        target_language: str = "vi",
    ) -> DocumentQuestionValidation:
        return DocumentQuestionValidation(
            result={
                "answerable": True,
                "singleBestAnswer": True,
                "correctAnswerSupported": True,
                "qualityScore": 0.86,
                "issues": [],
                "rationale": "Mock validation passed.",
            },
            model="mock-document-generator",
            prompt_version="mock-document-generator-v1",
        )

    @staticmethod
    def _source_excerpt(chunk_text: str) -> str:
        compact = re.sub(r"\s+", " ", chunk_text).strip()
        for sentence in re.split(r"(?<=[.!?。！？])\s+", compact):
            if len(sentence) >= 40:
                return sentence[:240].strip()
        return compact[:240].strip() or "Tài liệu không có đủ nội dung để trích dẫn."

    @staticmethod
    def _topic(excerpt: str) -> str:
        words = excerpt.split()
        topic = " ".join(words[:12]).strip(" ,.;:")
        return topic or "đoạn tài liệu"


class DeepSeekDocumentQuestionGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_questions(
        self,
        *,
        chunk_text: str,
        questions_per_chunk: int,
        target_language: str = "vi",
    ) -> DocumentQuestionBatch:
        if not self.settings.generation_api_key:
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "Chưa cấu hình DeepSeek API key",
                status_code=503,
            )
        total_usage = DocumentGenerationUsage()
        knowledge_points = self._extract_knowledge_points(chunk_text, total_usage)
        if not knowledge_points:
            return DocumentQuestionBatch(
                questions=[],
                model=self.settings.generation_model,
                usage=total_usage,
                knowledge_points=[],
            )
        payload = self._payload(
            chunk_text,
            questions_per_chunk,
            target_language,
            knowledge_points,
        )
        response, usage, model = self._call_with_fallback(payload)
        total_usage.add(usage)
        questions = response.get("questions")
        if not isinstance(questions, list):
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "DeepSeek không trả về danh sách questions hợp lệ",
                status_code=503,
                details={"response": response},
            )
        return DocumentQuestionBatch(
            questions=[item for item in questions if isinstance(item, dict)][:questions_per_chunk],
            model=model,
            usage=total_usage,
            knowledge_points=knowledge_points,
        )

    def _extract_knowledge_points(
        self,
        chunk_text: str,
        total_usage: DocumentGenerationUsage,
    ) -> list[dict[str, Any]]:
        payload = self._knowledge_payload(chunk_text)
        response, usage, _ = self._call_with_fallback(payload)
        total_usage.add(usage)
        items = response.get("knowledgePoints")
        if not isinstance(items, list):
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "DeepSeek không trả về danh sách knowledgePoints hợp lệ",
                status_code=503,
                details={"response": response},
            )
        return [item for item in items if isinstance(item, dict)][:8]

    def _knowledge_payload(self, chunk_text: str) -> dict[str, Any]:
        schema = {
            "knowledgePoints": [
                {
                    "id": "KP1",
                    "statement": "...",
                    "type": "definition|principle|procedure|warning|fact",
                    "importance": "low|medium|high",
                    "sourceExcerpt": "...",
                }
            ]
        }
        user_prompt = f"""Bạn phải trả về JSON hợp lệ.
Dựa CHỈ trên đoạn tài liệu dưới đây, trích xuất tối đa 8 knowledge point có thể dùng để tạo câu hỏi trắc nghiệm điều dưỡng/y khoa.
Chỉ lấy kiến thức có thể kiểm tra được bằng câu hỏi.
Không thêm kiến thức ngoài đoạn tài liệu.
sourceExcerpt phải là một câu hoặc cụm ngắn xuất hiện nguyên văn hoặc gần nguyên văn trong đoạn tài liệu.
Nếu đoạn tài liệu không có kiến thức kiểm tra được, trả về {{"knowledgePoints":[]}}.

Đoạn tài liệu:
{chunk_text}

JSON schema:
{json.dumps(schema, ensure_ascii=False)}"""
        return {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Bạn là trợ lý trích xuất kiến thức từ tài liệu y khoa. "
                        "Chỉ trả về JSON hợp lệ, không markdown."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "task": "knowledge_extraction",
        }

    def _payload(
        self,
        chunk_text: str,
        questions_per_chunk: int,
        target_language: str,
        knowledge_points: list[dict[str, Any]],
    ) -> dict[str, Any]:
        schema = {
            "questions": [
                {
                    "stem": "...",
                    "optionA": "...",
                    "optionB": "...",
                    "optionC": "...",
                    "optionD": "...",
                    "correctAnswer": "A",
                    "explanation": "...",
                    "difficulty": "medium",
                    "topic": "...",
                    "sourceExcerpt": "...",
                    "knowledgePointId": "KP1",
                }
            ]
        }
        user_prompt = f"""Bạn phải trả về JSON hợp lệ.
Dựa CHỈ trên knowledge point và đoạn tài liệu dưới đây, tạo {questions_per_chunk} câu hỏi trắc nghiệm điều dưỡng/y khoa.
Mỗi câu có 4 đáp án A/B/C/D và đúng đúng 1 đáp án.
Không dùng kiến thức ngoài đoạn tài liệu.
Không tạo câu hỏi nếu đoạn tài liệu không đủ thông tin.
sourceExcerpt phải là một câu hoặc cụm ngắn xuất hiện trong đoạn tài liệu.
Không dùng đáp án kiểu "tất cả đều đúng", "cả A và B", "không có đáp án nào".
Distractor phải cùng loại với đáp án đúng và nghe hợp lý nhưng sai theo nguồn.
Giải thích phải nêu vì sao đáp án đúng bám nguồn.
Ngôn ngữ: {target_language}

Knowledge points:
{json.dumps(knowledge_points, ensure_ascii=False)}

Đoạn tài liệu:
{chunk_text}

Trả về JSON đúng schema:
{json.dumps(schema, ensure_ascii=False)}"""
        return {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Bạn là trợ lý tạo câu hỏi trắc nghiệm từ tài liệu. "
                        "Luôn trả về JSON hợp lệ, không thêm chữ ngoài JSON. "
                        "Ưu tiên đúng nguồn, đúng một đáp án, và tiếng Việt rõ ràng."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "task": "question_generation",
        }

    def validate_question(
        self,
        *,
        chunk_text: str,
        question: dict[str, Any],
        target_language: str = "vi",
    ) -> DocumentQuestionValidation:
        payload = self._validation_payload(chunk_text, question, target_language)
        response, usage, model = self._call_with_fallback(payload)
        return DocumentQuestionValidation(
            result=response,
            model=model,
            usage=usage,
        )

    def _validation_payload(
        self,
        chunk_text: str,
        question: dict[str, Any],
        target_language: str,
    ) -> dict[str, Any]:
        schema = {
            "answerable": True,
            "singleBestAnswer": True,
            "correctAnswerSupported": True,
            "qualityScore": 0.0,
            "issues": ["..."],
            "rationale": "...",
        }
        user_prompt = f"""Bạn phải trả về JSON hợp lệ.
Kiểm định một câu hỏi trắc nghiệm được tạo từ tài liệu y khoa.
Dựa CHỈ trên đoạn tài liệu nguồn, đánh giá:
1. answerable: câu hỏi có trả lời được từ nguồn không.
2. singleBestAnswer: có đúng một đáp án tốt nhất không.
3. correctAnswerSupported: đáp án đúng có được nguồn hỗ trợ không.
4. qualityScore: số từ 0 đến 1, ưu tiên đúng nguồn, rõ tiếng Việt, distractor hợp lý.
5. issues: danh sách mã lỗi ngắn nếu có, ví dụ NOT_ANSWERABLE, MULTIPLE_VALID_OPTIONS, UNSUPPORTED_CORRECT_ANSWER, WEAK_DISTRACTORS.

Không dùng kiến thức ngoài đoạn tài liệu.
Ngôn ngữ phản hồi rationale: {target_language}

Đoạn tài liệu nguồn:
{chunk_text}

Câu hỏi ứng viên:
{json.dumps(question, ensure_ascii=False)}

JSON schema:
{json.dumps(schema, ensure_ascii=False)}"""
        return {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Bạn là bộ kiểm định câu hỏi trắc nghiệm từ tài liệu. "
                        "Chỉ trả về JSON hợp lệ, không markdown."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "task": "question_validation",
        }

    def _call_with_fallback(
        self, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], DocumentGenerationUsage, str]:
        models = [self.settings.generation_model]
        if self.settings.generation_fallback_model not in models:
            models.append(self.settings.generation_fallback_model)
        last_error: str | None = None
        for model in models:
            for _ in range(self.settings.generation_max_retries + 1):
                try:
                    return self._call_model(model, payload)
                except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
                    last_error = str(exc)
        raise AppError(
            ErrorCode.GENERATION_FAILED,
            "Không thể tạo câu hỏi từ tài liệu bằng DeepSeek API",
            status_code=503,
            details={"reason": last_error},
        )

    def _call_model(
        self, model: str, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], DocumentGenerationUsage, str]:
        url = f"{self.settings.generation_api_base_url.rstrip('/')}/chat/completions"
        started = time.perf_counter()
        request_json = {
            "model": model,
            "messages": payload["messages"],
            "temperature": payload["temperature"],
            "response_format": payload["response_format"],
        }
        with httpx.Client(timeout=self.settings.generation_timeout_seconds) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.settings.generation_api_key}",
                    "Content-Type": "application/json",
                },
                json=request_json,
            )
            response.raise_for_status()
            response_data = response.json()
            content = response_data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("DeepSeek response is not a JSON object")
        raw_usage = response_data.get("usage") or {}
        usage = DocumentGenerationUsage(
            prompt_tokens=int(raw_usage.get("prompt_tokens") or 0),
            completion_tokens=int(raw_usage.get("completion_tokens") or 0),
            total_tokens=int(raw_usage.get("total_tokens") or 0),
            latency_ms=int((time.perf_counter() - started) * 1000),
            call_count=1,
        )
        return parsed, usage, model
