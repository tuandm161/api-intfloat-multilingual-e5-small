"""Local model generator adapter stub."""

from app.core.enums import ErrorCode
from app.core.errors import AppError
from app.modules.paraphrase.providers.base import GenerateRequest


class LocalParaphraseGenerator:
    def generate_stem_paraphrases(self, request: GenerateRequest) -> list[str]:
        raise AppError(
            ErrorCode.GENERATION_FAILED,
            "Nhà cung cấp mô hình cục bộ chưa được cấu hình",
            status_code=503,
        )
