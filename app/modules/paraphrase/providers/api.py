"""External API generator adapter for DeepSeek's OpenAI-compatible API."""

import json
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.enums import ErrorCode
from app.core.errors import AppError
from app.modules.normalization.text_builders import ParaphrasePromptBuilder
from app.modules.paraphrase.providers.base import GenerateRequest


class ApiParaphraseGenerator:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def generate_stem_paraphrases(self, request: GenerateRequest) -> list[str]:
        if not self.settings.generation_api_key:
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "Chưa cấu hình DeepSeek API key",
                status_code=503,
            )

        prompt = ParaphrasePromptBuilder.build_stem_only_prompt(
            request.source,
            request.requested_count,
            request.target_language,
            request.change_strength,
        )
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Bạn là trợ lý tạo câu hỏi điều dưỡng/y khoa an toàn. "
                        "Luôn trả về JSON hợp lệ, không thêm chữ ngoài JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
        }
        response = self._call_with_fallback(payload)
        return self._parse_stems(response, request.requested_count)

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
            "Không thể tạo câu diễn đạt lại bằng DeepSeek API",
            status_code=503,
            details={"reason": last_error},
        )

    def _call_model(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.settings.generation_api_base_url.rstrip('/')}/chat/completions"
        request_payload = {"model": model, **payload}
        with httpx.Client(timeout=self.settings.generation_timeout_seconds) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.settings.generation_api_key}",
                    "Content-Type": "application/json",
                },
                json=request_payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("DeepSeek response is not a JSON object")
        return parsed

    @staticmethod
    def _parse_stems(data: dict[str, Any], requested_count: int) -> list[str]:
        raw_items = data.get("candidates")
        if not isinstance(raw_items, list):
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "DeepSeek không trả về danh sách candidates hợp lệ",
                status_code=503,
                details={"response": data},
            )
        stems = []
        for item in raw_items:
            if isinstance(item, dict):
                stem = str(item.get("stem") or "").strip()
                if stem:
                    stems.append(stem)
        if not stems:
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "DeepSeek không trả về câu diễn đạt lại hợp lệ",
                status_code=503,
                details={"response": data},
            )
        return stems[:requested_count]
