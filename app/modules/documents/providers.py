"""Question generation providers for document chunks."""

import json
import re
from typing import Any

import httpx

from app.core.config import Settings
from app.core.enums import ErrorCode
from app.core.errors import AppError


class MockDocumentQuestionGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_questions(
        self,
        *,
        chunk_text: str,
        questions_per_chunk: int,
        target_language: str = "vi",
    ) -> list[dict[str, Any]]:
        excerpt = self._source_excerpt(chunk_text)
        topic = self._topic(excerpt)
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
        return questions

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
    ) -> list[dict[str, Any]]:
        if not self.settings.generation_api_key:
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "Chưa cấu hình DeepSeek API key",
                status_code=503,
            )
        payload = self._payload(chunk_text, questions_per_chunk, target_language)
        response = self._call_with_fallback(payload)
        questions = response.get("questions")
        if not isinstance(questions, list):
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "DeepSeek không trả về danh sách questions hợp lệ",
                status_code=503,
                details={"response": response},
            )
        return [item for item in questions if isinstance(item, dict)][:questions_per_chunk]

    def _payload(
        self,
        chunk_text: str,
        questions_per_chunk: int,
        target_language: str,
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
                }
            ]
        }
        user_prompt = f"""Dựa CHỈ trên đoạn tài liệu dưới đây, tạo {questions_per_chunk} câu hỏi trắc nghiệm điều dưỡng/y khoa.
Mỗi câu có 4 đáp án A/B/C/D và đúng đúng 1 đáp án.
Không dùng kiến thức ngoài đoạn tài liệu.
Không tạo câu hỏi nếu đoạn tài liệu không đủ thông tin.
sourceExcerpt phải là một câu hoặc cụm ngắn xuất hiện trong đoạn tài liệu.
Ngôn ngữ: {target_language}

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
                        "Luôn trả về JSON hợp lệ, không thêm chữ ngoài JSON."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }

    def _call_with_fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
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

    def _call_model(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.settings.generation_api_base_url.rstrip('/')}/chat/completions"
        with httpx.Client(timeout=self.settings.generation_timeout_seconds) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.settings.generation_api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": model, **payload},
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("DeepSeek response is not a JSON object")
        return parsed
