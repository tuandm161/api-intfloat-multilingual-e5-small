"""VietQuill-backed local Vietnamese paraphrase generator."""

from functools import lru_cache
from typing import Any

from app.core.config import Settings, get_settings
from app.core.enums import ErrorCode
from app.core.errors import AppError
from app.modules.paraphrase.providers.base import GenerateRequest, GeneratedParaphrase
from app.modules.paraphrase.providers.local import (
    _clean_generated_field_text,
    _generation_candidate_count,
    _missing_protected_terms_by_field,
    _normalize_candidate,
    _protected_terms_by_field,
)


def _vietquill_cache_key(settings: Settings) -> tuple[str, str]:
    return (settings.vietquill_model_repo_id, settings.vietquill_device)


@lru_cache(maxsize=2)
def _load_vietquill_model(repo_id: str, device: str):
    try:
        from vietquill import AutoModelForControllableParaphraseGeneration
    except ImportError as exc:
        raise AppError(
            ErrorCode.GENERATION_FAILED,
            "Thiếu thư viện vietquill để chạy mô hình paraphrase tiếng Việt cục bộ",
            status_code=503,
            details={"package": "vietquill"},
        ) from exc

    try:
        return AutoModelForControllableParaphraseGeneration(
            hub_id=repo_id,
            device=device or None,
        )
    except Exception as exc:
        raise AppError(
            ErrorCode.GENERATION_FAILED,
            "Không thể tải mô hình VietQuill cục bộ",
            status_code=503,
            details={"repoId": repo_id, "device": device, "reason": str(exc)},
        ) from exc


def get_vietquill_model(settings: Settings):
    return _load_vietquill_model(*_vietquill_cache_key(settings))


class VietQuillParaphraseGenerator:
    def __init__(self, settings: Settings | None = None, model: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self._model = model

    def generate_paraphrases(self, request: GenerateRequest) -> list[GeneratedParaphrase]:
        model = self._model or get_vietquill_model(self.settings)
        protected_terms = _protected_terms_by_field(request.source)
        target_count = max(8, _generation_candidate_count(request.requested_count))

        try:
            stems = self._generate_field_candidates(
                model,
                request.source.stem,
                field="stem",
                count=target_count,
            )
            options_a = self._generate_field_candidates(
                model,
                request.source.option_a,
                field="optionA",
                count=target_count,
            )
            options_b = self._generate_field_candidates(
                model,
                request.source.option_b,
                field="optionB",
                count=target_count,
            )
            options_c = self._generate_field_candidates(
                model,
                request.source.option_c,
                field="optionC",
                count=target_count,
            )
            options_d = self._generate_field_candidates(
                model,
                request.source.option_d,
                field="optionD",
                count=target_count,
            )
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "Không thể tạo câu diễn đạt lại bằng VietQuill",
                status_code=503,
                details={"reason": str(exc)},
            ) from exc

        raw_candidates = []
        max_items = max(
            len(stems),
            len(options_a),
            len(options_b),
            len(options_c),
            len(options_d),
            0,
        )
        for index in range(max_items):
            if not all((stems, options_a, options_b, options_c, options_d)):
                break
            raw_candidates.append(
                _normalize_candidate(
                    GeneratedParaphrase(
                        stems[index % len(stems)],
                        options_a[index % len(options_a)],
                        options_b[index % len(options_b)],
                        options_c[index % len(options_c)],
                        options_d[index % len(options_d)],
                    )
                )
            )
        filtered, stats = self._filter_candidates(request, raw_candidates, protected_terms)
        if len(filtered) >= request.requested_count:
            return filtered[: request.requested_count]

        raise AppError(
            ErrorCode.GENERATION_FAILED,
            "VietQuill không tạo được câu diễn đạt lại hợp lệ",
            status_code=503,
            details={
                "reason": (
                    f"not_enough_valid_candidates: {len(filtered)}/{request.requested_count}; "
                    f"{stats['reason'] or 'no_valid_candidates'}"
                ),
                "protectedTerms": protected_terms,
                "requestedCount": request.requested_count,
                "generatedCount": len(raw_candidates),
            },
        )

    def _generate_field_candidates(
        self,
        model: Any,
        text: str,
        *,
        field: str,
        count: int,
    ) -> list[str]:
        raw_candidates = model.paraphrase(
            text,
            style=self._style(field),
            num_candidates=count,
            num_beams=max(self.settings.vietquill_num_beams, count + 2),
            max_length=self.settings.vietquill_max_length,
        )
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in raw_candidates:
            candidate = _clean_generated_field_text(str(raw), field)
            normalized = candidate.casefold()
            if candidate and normalized not in seen:
                cleaned.append(candidate)
                seen.add(normalized)
        return cleaned

    def _style(self, field: str) -> str:
        if field != "stem":
            return "conservative"
        if self.settings.vietquill_style in {"conservative", "balanced", "diverse"}:
            return self.settings.vietquill_style
        return "balanced"

    @staticmethod
    def _filter_candidates(
        request: GenerateRequest,
        candidates: list[GeneratedParaphrase],
        protected_terms: dict[str, list[str]],
    ):
        from app.modules.paraphrase.providers.local import LocalParaphraseGenerator

        filtered, stats = LocalParaphraseGenerator._filter_candidates(
            request,
            candidates,
            protected_terms,
            min_lexical_difference=0.05,
        )
        if not filtered and not stats["reason"] and candidates:
            missing = _missing_protected_terms_by_field(candidates[0], protected_terms)
            if missing:
                stats["reason"] = f"missing_required_terms: {', '.join(missing)}"
        return filtered, stats
