"""Local Qwen GGUF paraphrase generator."""

from functools import lru_cache
import json
import re
from typing import Any

from app.core.config import Settings, get_settings
from app.core.enums import ErrorCode
from app.core.errors import AppError
from app.modules.normalization.text_normalizer import TextNormalizer
from app.modules.paraphrase.providers.base import GenerateRequest, GeneratedParaphrase
from app.modules.validation.lexical import calculate_lexical_difference
from app.modules.validation.rules import contains_answer_hint, contains_option_content


MIN_GENERATION_LEXICAL_DIFFERENCE = 0.25

SYSTEM_PROMPT = (
    "Bạn là trợ lý tạo câu hỏi điều dưỡng/y khoa an toàn.\n"
    "Chỉ viết lại văn bản được yêu cầu, không giải thích.\n"
    "Luôn dùng tiếng Việt có dấu UTF-8; không thay chữ có dấu bằng dấu hỏi.\n"
    "Không tự thêm kiến thức y khoa mới."
)

FIELD_SPECS = {
    "stem": ("QUESTION_STEM", "stem"),
    "optionA": ("OPTION_A", "option_a"),
    "optionB": ("OPTION_B", "option_b"),
    "optionC": ("OPTION_C", "option_c"),
    "optionD": ("OPTION_D", "option_d"),
}


def _model_cache_key(settings: Settings) -> tuple[str, str, int, int, int]:
    return (
        settings.local_paraphrase_model_repo_id,
        settings.local_paraphrase_model_filename,
        settings.local_paraphrase_context_tokens,
        settings.local_paraphrase_threads,
        settings.local_paraphrase_gpu_layers,
    )


@lru_cache(maxsize=2)
def _load_llama_model(
    repo_id: str,
    filename: str,
    n_ctx: int,
    n_threads: int,
    n_gpu_layers: int,
):
    try:
        from llama_cpp import Llama
    except ImportError as exc:
        raise AppError(
            ErrorCode.GENERATION_FAILED,
            "Thiếu thư viện llama-cpp-python để chạy mô hình cục bộ",
            status_code=503,
            details={"package": "llama-cpp-python"},
        ) from exc

    try:
        return Llama.from_pretrained(
            repo_id=repo_id,
            filename=filename,
            n_ctx=n_ctx,
            n_threads=n_threads or None,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )
    except Exception as exc:
        raise AppError(
            ErrorCode.GENERATION_FAILED,
            "Không thể tải mô hình paraphrase cục bộ",
            status_code=503,
            details={"repoId": repo_id, "filename": filename, "reason": str(exc)},
        ) from exc


def get_local_llama_model(settings: Settings):
    return _load_llama_model(*_model_cache_key(settings))


def _generation_candidate_count(requested_count: int) -> int:
    return min(10, requested_count + 2)


class LocalParaphraseGenerator:
    def __init__(self, settings: Settings | None = None, model: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self._model = model

    def generate_paraphrases(self, request: GenerateRequest) -> list[GeneratedParaphrase]:
        model = self._model or get_local_llama_model(self.settings)
        protected_terms = _protected_terms_by_field(request.source)
        last_error: AppError | None = None
        last_filter_reason = ""
        target_count = _generation_candidate_count(request.requested_count)
        max_candidate_attempts = max(target_count, request.requested_count * 3)
        raw_candidates: list[GeneratedParaphrase] = []

        for attempt in range(max_candidate_attempts):
            try:
                raw_candidates.append(
                    self._generate_candidate_fields(
                        model,
                        request,
                        protected_terms,
                        candidate_index=attempt + 1,
                        retry_reason=last_filter_reason or None,
                    )
                )
            except AppError as exc:
                last_error = exc
                last_filter_reason = str(exc.details.get("reason") or exc.message)
                continue

            filtered, stats = self._filter_candidates(
                request,
                raw_candidates,
                protected_terms,
                min_lexical_difference=self.settings.validation_lexical_too_different_min,
            )
            if len(filtered) >= request.requested_count:
                return filtered[: request.requested_count]

            last_filter_reason = (
                f"not_enough_valid_candidates: {len(filtered)}/{request.requested_count}; "
                f"{stats['reason'] or 'no_valid_candidates'}"
            )

        if last_error is not None and not raw_candidates:
            raise last_error
        raise AppError(
            ErrorCode.GENERATION_FAILED,
            "Mô hình cục bộ không tạo được câu diễn đạt lại hợp lệ",
            status_code=503,
            details={
                "reason": last_filter_reason or "no_valid_candidates",
                "protectedTerms": protected_terms,
                "requestedCount": request.requested_count,
            },
        )

    def _generate_candidate_fields(
        self,
        model: Any,
        request: GenerateRequest,
        protected_terms: dict[str, list[str]],
        *,
        candidate_index: int,
        retry_reason: str | None = None,
    ) -> GeneratedParaphrase:
        stem = self._generate_single_field(
            model,
            request,
            field="stem",
            protected_terms=protected_terms["stem"],
            candidate_index=candidate_index,
            retry_reason=retry_reason,
        )
        option_a = self._generate_single_field(
            model,
            request,
            field="optionA",
            protected_terms=protected_terms["optionA"],
            candidate_index=candidate_index,
            rewritten_stem=stem,
            retry_reason=retry_reason,
        )
        option_b = self._generate_single_field(
            model,
            request,
            field="optionB",
            protected_terms=protected_terms["optionB"],
            candidate_index=candidate_index,
            rewritten_stem=stem,
            retry_reason=retry_reason,
        )
        option_c = self._generate_single_field(
            model,
            request,
            field="optionC",
            protected_terms=protected_terms["optionC"],
            candidate_index=candidate_index,
            rewritten_stem=stem,
            retry_reason=retry_reason,
        )
        option_d = self._generate_single_field(
            model,
            request,
            field="optionD",
            protected_terms=protected_terms["optionD"],
            candidate_index=candidate_index,
            rewritten_stem=stem,
            retry_reason=retry_reason,
        )
        return _normalize_candidate(
            GeneratedParaphrase(stem, option_a, option_b, option_c, option_d)
        )

    def _generate_single_field(
        self,
        model: Any,
        request: GenerateRequest,
        *,
        field: str,
        protected_terms: list[str],
        candidate_index: int,
        rewritten_stem: str | None = None,
        retry_reason: str | None = None,
    ) -> str:
        try:
            response = model.create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": self._build_field_prompt(
                            request,
                            field=field,
                            protected_terms=protected_terms,
                            candidate_index=candidate_index,
                            rewritten_stem=rewritten_stem,
                            retry_reason=retry_reason,
                        ),
                    },
                ],
                temperature=self.settings.local_paraphrase_temperature,
                top_p=self.settings.local_paraphrase_top_p,
                repeat_penalty=self.settings.local_paraphrase_repeat_penalty,
                max_tokens=min(self.settings.local_paraphrase_max_tokens, 256),
                stop=["<|im_end|>", "<|endoftext|>"],
            )
            raw_content = str(response["choices"][0]["message"]["content"])
            return self._parse_field_text(raw_content, field)
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "Không thể tạo câu diễn đạt lại bằng mô hình cục bộ",
                status_code=503,
                details={"reason": str(exc), "field": field},
            ) from exc

    @staticmethod
    def _build_field_prompt(
        request: GenerateRequest,
        *,
        field: str,
        protected_terms: list[str],
        candidate_index: int,
        rewritten_stem: str | None = None,
        retry_reason: str | None = None,
    ) -> str:
        field_label, source_attr = FIELD_SPECS[field]
        source = request.source
        original_text = getattr(source, source_attr)
        protected_text = ", ".join(protected_terms) if protected_terms else "(không có)"
        retry_block = (
            f"\nLần trước bị loại vì: {retry_reason}. Hãy viết khác rõ hơn và vẫn giữ đúng nghĩa.\n"
            if retry_reason
            else ""
        )
        task_focus = ""
        context_block = ""
        if field != "stem":
            task_focus = (
                f"Bạn chỉ được viết lại nội dung của {field_label}. "
                "Không viết lại câu hỏi, không copy QUESTION_STEM vào đáp án."
            )
            context_block = f"""
Ngữ cảnh để hiểu đáp án, không được sao chép:
- QUESTION_STEM nguồn: {source.stem}
- QUESTION_STEM đã viết lại: {rewritten_stem}
- Đáp án đúng vẫn do hệ thống giữ là {source.correct_answer}; không nhắc đáp án đúng trong output.
"""
        else:
            task_focus = (
                "Bạn chỉ được viết lại câu hỏi. Không đưa nội dung cụ thể của các đáp án vào câu hỏi."
            )
            context_block = f"""
Các đáp án nguồn chỉ để hiểu ngữ cảnh, không đưa nội dung đáp án vào câu hỏi:
A. {source.option_a}
B. {source.option_b}
C. {source.option_c}
D. {source.option_d}
"""
        return f"""Viết lại riêng trường {field_label} của một câu hỏi trắc nghiệm điều dưỡng/y khoa.
{task_focus}
Chỉ trả về đúng một dòng tiếng Việt có dấu đã viết lại cho {field_label}; không JSON, không markdown, không nhãn field.

Quy tắc:
- Giữ nguyên ý nghĩa y khoa và mức độ đúng/sai của trường này.
- Không thêm kiến thức mới, không giải thích, không trả lời câu hỏi.
- Giữ nguyên chính xác các thuật ngữ/số liệu/đơn vị bắt buộc trong trường này: {protected_text}.
- Không sao chép nguyên văn; đổi cách diễn đạt đủ rõ nhưng không làm dài dòng.
- Không dùng dấu ? để thay thế chữ tiếng Việt có dấu.
- Ngôn ngữ đích: {request.target_language}; mức thay đổi: {request.change_strength}.
- Đây là biến thể số {candidate_index}, hãy dùng cách diễn đạt khác các biến thể trước nếu có.
{retry_block}

{field_label} nguồn:
{original_text}

{context_block}

{field_label} viết lại:"""

    @classmethod
    def _parse_field_text(cls, raw_content: str, field: str) -> str:
        text = raw_content.strip()
        try:
            parsed = cls._parse_json_object(text)
        except AppError:
            parsed = None
        if isinstance(parsed, dict):
            for key in (
                field,
                FIELD_SPECS[field][0],
                "text",
                "rewrite",
                "rewritten",
                "paraphrase",
                "answer",
            ):
                value = parsed.get(key)
                if isinstance(value, str) and value.strip():
                    text = value.strip()
                    break
        text = _clean_generated_field_text(text, field)
        if not text:
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "Mô hình cục bộ trả về field rỗng",
                status_code=503,
                details={"field": field, "response": raw_content},
            )
        return text

    def _generate_content(
        self,
        model: Any,
        request: GenerateRequest,
        *,
        retry_terms: dict[str, list[str]] | None = None,
        retry_reason: str | None = None,
    ) -> str:
        try:
            response = model.create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": self._build_user_prompt(
                            request,
                            retry_terms=retry_terms,
                            retry_reason=retry_reason,
                        ),
                    },
                ],
                temperature=self.settings.local_paraphrase_temperature,
                top_p=self.settings.local_paraphrase_top_p,
                repeat_penalty=self.settings.local_paraphrase_repeat_penalty,
                max_tokens=self.settings.local_paraphrase_max_tokens,
                stop=["<|im_end|>", "<|endoftext|>"],
                response_format={"type": "json_object"},
            )
            return str(response["choices"][0]["message"]["content"])
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "Không thể tạo câu diễn đạt lại bằng mô hình cục bộ",
                status_code=503,
                details={"reason": str(exc)},
            ) from exc

    @staticmethod
    def _build_user_prompt(
        request: GenerateRequest,
        *,
        retry_terms: dict[str, list[str]] | None = None,
        retry_reason: str | None = None,
    ) -> str:
        candidate_count = _generation_candidate_count(request.requested_count)
        schema = json.dumps(
            {
                "candidates": [
                    {
                        "stem": "...",
                        "optionA": "...",
                        "optionB": "...",
                        "optionC": "...",
                        "optionD": "...",
                    }
                    for _ in range(candidate_count)
                ]
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        source = request.source
        retry_block = ""
        if retry_terms is not None:
            terms = _format_protected_terms(retry_terms)
            retry_block = (
                "\nThe previous output was invalid or removed required terms.\n"
                f"Reason: {retry_reason or 'invalid_or_filtered_output'}.\n"
                f"You must keep these exact terms unchanged: {terms}.\n"
                f"You must return at least {request.requested_count} valid, different stems.\n"
                "Do not copy the original stem; change the wording more clearly.\n"
                "Return valid JSON only.\n"
            )
        return f"""Viết lại cả câu hỏi trắc nghiệm điều dưỡng/y khoa gồm QUESTION_STEM và 4 OPTIONS.
Phải phân tách rõ từng trường; không gộp đáp án vào stem và không chuyển nội dung giữa các option.
Không trả lời câu hỏi trong stem.
Không đổi ý nghĩa y khoa, bối cảnh, dấu hiệu cảnh báo, ngưỡng, hoặc chiều so sánh của từng trường.
Ví dụ: "dưới 90 mmHg" vẫn phải mang nghĩa dưới 90 mmHg; không đổi thành đạt 90 mmHg.
Không thêm kiến thức y khoa mới.
Không làm lộ đáp án đúng.
Giữ nguyên chính xác mọi thuật ngữ tiếng Anh, viết tắt, số liệu, dấu so sánh và đơn vị trong đúng trường gốc.
Không sao chép nguyên văn stem/options gốc; phải thay đổi cách diễn đạt rõ ràng nhưng vẫn giữ cùng vai trò đáp án.
Giữ đúng thứ tự OPTION_A, OPTION_B, OPTION_C, OPTION_D; đáp án đúng vẫn là cùng chữ cái như ban đầu.
Trả về đúng {candidate_count} candidates khác nhau để hệ thống lọc lấy {request.requested_count} câu tốt nhất.
Ngôn ngữ đích: {request.target_language}
Mức độ thay đổi: {request.change_strength}
{retry_block}

Cấu trúc dữ liệu trong hệ thống:
- QUESTION_STEM: viết lại câu hỏi, không chứa nội dung của option.
- OPTION_A, OPTION_B, OPTION_C, OPTION_D: viết lại từng đáp án riêng, không đổi thứ tự.
- CORRECT_ANSWER: giữ nguyên bên ngoài model là {source.correct_answer}; không đưa vào JSON.

Ví dụ:
- Gốc: "Trong cấp cứu, ưu tiên ABC nhằm mục đích gì?"
- Viết lại: "Mục đích của việc ưu tiên ABC trong tình huống cấp cứu là gì?"
- Option gốc: "Đảm bảo sự sống còn của người bệnh."
- Option viết lại: "Duy trì các chức năng sống thiết yếu của người bệnh."

QUESTION_STEM gốc:
{source.stem}

OPTION_A gốc:
{source.option_a}

OPTION_B gốc:
{source.option_b}

OPTION_C gốc:
{source.option_c}

OPTION_D gốc:
{source.option_d}

Chỉ trả về JSON hợp lệ, không markdown, không giải thích.
Return JSON only:
{schema}"""

    @staticmethod
    def _filter_candidates(
        request: GenerateRequest,
        candidates: list[GeneratedParaphrase],
        protected_terms: dict[str, list[str]],
        *,
        min_lexical_difference: float = MIN_GENERATION_LEXICAL_DIFFERENCE,
    ) -> tuple[list[GeneratedParaphrase], dict[str, int | str]]:
        source_normalized = TextNormalizer.normalize_for_comparison(request.source.stem)
        correct_option = getattr(
            request.source, f"option_{request.source.correct_answer.lower()}"
        )
        option_texts = _source_option_texts(request.source)
        seen: set[str] = set()
        filtered: list[GeneratedParaphrase] = []
        stats: dict[str, int | str] = {
            "empty": 0,
            "corrupted_text": 0,
            "source_duplicate": 0,
            "too_similar": 0,
            "field_duplicate": 0,
            "candidate_duplicate": 0,
            "missing_terms": 0,
            "answer_hint": 0,
            "reason": "",
        }

        for candidate in candidates:
            display = _normalize_candidate(candidate)
            normalized = TextNormalizer.normalize_for_comparison(display.stem)
            full_text = _candidate_full_text(display)
            normalized_full = TextNormalizer.normalize_for_comparison(full_text)
            if not _candidate_fields_present(display):
                stats["empty"] = int(stats["empty"]) + 1
                continue
            if _looks_corrupted_candidate(display):
                stats["corrupted_text"] = int(stats["corrupted_text"]) + 1
                stats["reason"] = "corrupted_text"
                continue
            if normalized == source_normalized:
                stats["source_duplicate"] = int(stats["source_duplicate"]) + 1
                stats["reason"] = "source_duplicate"
                continue
            if (
                calculate_lexical_difference(request.source.stem, display.stem)
                < min_lexical_difference
            ):
                stats["too_similar"] = int(stats["too_similar"]) + 1
                stats["reason"] = "too_similar_to_source"
                continue
            if _has_unparaphrased_field(request.source, display):
                stats["field_duplicate"] = int(stats["field_duplicate"]) + 1
                stats["reason"] = "field_duplicate"
                continue
            if normalized_full in seen:
                stats["candidate_duplicate"] = int(stats["candidate_duplicate"]) + 1
                continue
            if missing := _missing_protected_terms_by_field(display, protected_terms):
                stats["missing_terms"] = int(stats["missing_terms"]) + 1
                stats["reason"] = f"missing_required_terms: {', '.join(missing)}"
                continue
            if contains_answer_hint(display.stem, correct_option) or contains_option_content(
                display.stem, request.source.stem, option_texts
            ):
                stats["answer_hint"] = int(stats["answer_hint"]) + 1
                stats["reason"] = "contains_answer_hint"
                continue
            seen.add(normalized_full)
            filtered.append(display)

        if not filtered and not stats["reason"]:
            for key in (
                "empty",
                "corrupted_text",
                "source_duplicate",
                "field_duplicate",
                "candidate_duplicate",
            ):
                if stats[key]:
                    stats["reason"] = key
                    break
        return filtered, stats

    @classmethod
    def _parse_candidates(cls, raw_content: str, requested_count: int) -> list[GeneratedParaphrase]:
        data = cls._parse_json_object(raw_content)
        raw_items = data.get("candidates")
        if not isinstance(raw_items, list):
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "Mô hình cục bộ không trả về danh sách candidates hợp lệ",
                status_code=503,
                details={"response": data},
            )

        candidates = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            candidate = GeneratedParaphrase(
                stem=str(item.get("stem") or "").strip(),
                option_a=str(item.get("optionA") or item.get("option_a") or "").strip(),
                option_b=str(item.get("optionB") or item.get("option_b") or "").strip(),
                option_c=str(item.get("optionC") or item.get("option_c") or "").strip(),
                option_d=str(item.get("optionD") or item.get("option_d") or "").strip(),
            )
            if _candidate_fields_present(candidate):
                candidates.append(candidate)
        if not candidates:
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "Mô hình cục bộ không trả về câu diễn đạt lại hợp lệ",
                status_code=503,
                details={"response": data},
            )
        return candidates[:requested_count]

    @staticmethod
    def _parse_json_object(raw_content: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError:
            start = raw_content.find("{")
            end = raw_content.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise AppError(
                    ErrorCode.GENERATION_FAILED,
                    "Mô hình cục bộ không trả về JSON hợp lệ",
                    status_code=503,
                    details={"response": raw_content},
                ) from None
            try:
                parsed = json.loads(raw_content[start : end + 1])
            except json.JSONDecodeError as exc:
                raise AppError(
                    ErrorCode.GENERATION_FAILED,
                    "Mô hình cục bộ không trả về JSON hợp lệ",
                    status_code=503,
                    details={"response": raw_content},
                ) from exc
        if not isinstance(parsed, dict):
            raise AppError(
                ErrorCode.GENERATION_FAILED,
                "Mô hình cục bộ không trả về JSON object hợp lệ",
                status_code=503,
                details={"response": parsed},
            )
        return parsed


class DisabledApiParaphraseGenerator:
    def generate_paraphrases(self, request: GenerateRequest) -> list[GeneratedParaphrase]:
        raise AppError(
            ErrorCode.GENERATION_FAILED,
            "API paraphrase provider is disabled; use local or mock provider.",
            status_code=503,
        )


def extract_protected_terms(text: str) -> list[str]:
    terms: list[str] = []

    def add(term: str) -> None:
        normalized = _normalize_term(term)
        if normalized and normalized not in {_normalize_term(item) for item in terms}:
            terms.append(term.strip())

    for match in re.finditer(r"\(([^)]*[A-Za-z][^)]*)\)", text):
        add(match.group(1))
    for match in re.finditer(r'"([^"]*[A-Za-z][^"]*)"', text):
        add(match.group(1))
    for match in re.finditer(r"'([^']*[A-Za-z][^']*)'", text):
        add(match.group(1))

    token_pattern = (
        r"\b(?:[A-Z]{2,}\d*|[A-Za-z]*[A-Z][a-z]*\d+[A-Za-z0-9]*|"
        r"[A-Za-z]+(?:[-/][A-Za-z0-9]+)+|mmHg|mmol/L|ml/kg/h|HbA1c|SpO2)\b"
    )
    for match in re.finditer(token_pattern, text):
        add(match.group(0))

    number_pattern = (
        r"(?:[<>]=?\s*)?\d+(?:[.,]\d+)?"
        r"(?:\s*(?:-|–|—)\s*\d+(?:[.,]\d+)?)?"
        r"(?:\s*(?:%|mmHg|mmol/L|ml/kg/h|lần/phút|phút|giờ|ngày))?"
    )
    for match in re.finditer(number_pattern, text):
        term = match.group(0).strip()
        if re.search(r"[<>%/]|(?:-|–|—)|[A-Za-zÀ-ỹ]", term):
            add(term)

    return terms


def missing_protected_terms(candidate: str, protected_terms: list[str]) -> list[str]:
    candidate_normalized = TextNormalizer.normalize_for_comparison(candidate)
    return [
        term
        for term in protected_terms
        if _normalize_term(term) not in candidate_normalized
    ]


def _source_option_texts(source: Any) -> tuple[str, str, str, str]:
    return (source.option_a, source.option_b, source.option_c, source.option_d)


def _protected_terms_by_field(source: Any) -> dict[str, list[str]]:
    return {
        "stem": extract_protected_terms(source.stem),
        "optionA": extract_protected_terms(source.option_a),
        "optionB": extract_protected_terms(source.option_b),
        "optionC": extract_protected_terms(source.option_c),
        "optionD": extract_protected_terms(source.option_d),
    }


def _format_protected_terms(terms_by_field: dict[str, list[str]]) -> str:
    parts = [
        f"{field}: {', '.join(terms)}"
        for field, terms in terms_by_field.items()
        if terms
    ]
    return "; ".join(parts) if parts else "(none)"


def _normalize_candidate(candidate: GeneratedParaphrase) -> GeneratedParaphrase:
    return GeneratedParaphrase(
        stem=TextNormalizer.normalize_for_display(candidate.stem),
        option_a=TextNormalizer.normalize_for_display(candidate.option_a),
        option_b=TextNormalizer.normalize_for_display(candidate.option_b),
        option_c=TextNormalizer.normalize_for_display(candidate.option_c),
        option_d=TextNormalizer.normalize_for_display(candidate.option_d),
    )


def _candidate_fields_present(candidate: GeneratedParaphrase) -> bool:
    return all(
        getattr(candidate, field)
        for field in ("stem", "option_a", "option_b", "option_c", "option_d")
    )


def _candidate_full_text(candidate: GeneratedParaphrase) -> str:
    return "\n".join(
        [
            f"Câu hỏi: {candidate.stem}",
            f"A. {candidate.option_a}",
            f"B. {candidate.option_b}",
            f"C. {candidate.option_c}",
            f"D. {candidate.option_d}",
        ]
    )


def _looks_corrupted_candidate(candidate: GeneratedParaphrase) -> bool:
    return any(
        _looks_corrupted_text(value)
        for value in (
            candidate.stem,
            candidate.option_a,
            candidate.option_b,
            candidate.option_c,
            candidate.option_d,
        )
    )


def _has_unparaphrased_field(source: Any, candidate: GeneratedParaphrase) -> bool:
    pairs = (
        (source.stem, candidate.stem),
        (source.option_a, candidate.option_a),
        (source.option_b, candidate.option_b),
        (source.option_c, candidate.option_c),
        (source.option_d, candidate.option_d),
    )
    return any(
        TextNormalizer.normalize_for_comparison(original)
        == TextNormalizer.normalize_for_comparison(rewritten)
        for original, rewritten in pairs
    )


def _missing_protected_terms_by_field(
    candidate: GeneratedParaphrase, protected_terms: dict[str, list[str]]
) -> list[str]:
    candidate_values = {
        "stem": candidate.stem,
        "optionA": candidate.option_a,
        "optionB": candidate.option_b,
        "optionC": candidate.option_c,
        "optionD": candidate.option_d,
    }
    missing: list[str] = []
    for field, terms in protected_terms.items():
        for term in missing_protected_terms(candidate_values[field], terms):
            missing.append(f"{field}:{term}")
    return missing


def _clean_generated_field_text(raw_text: str, field: str) -> str:
    text = raw_text.strip()
    text = re.sub(r"^```(?:json|text)?\s*", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s*```$", "", text).strip()
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        text = text[1:-1].strip()

    field_label = FIELD_SPECS[field][0]
    label_patterns = [
        field_label,
        field_label.replace("_", " "),
        field,
        "câu hỏi" if field == "stem" else f"đáp án {field[-1]}",
        f"option {field[-1]}" if field != "stem" else "question stem",
    ]
    for label in label_patterns:
        text = re.sub(
            rf"^\s*(?:[-*]\s*)?{re.escape(label)}\s*[:：.-]\s*",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        text = lines[0]
    text = re.sub(r"^\s*[-*]\s*", "", text).strip()
    if field != "stem":
        text = re.sub(rf"^\s*{field[-1]}\s*[.)]\s*", "", text, flags=re.IGNORECASE)
    return TextNormalizer.normalize_for_display(text)


def _looks_corrupted_text(text: str) -> bool:
    if "�" in text:
        return True
    if text.count("?") >= 3:
        return True
    return bool(re.search(r"\w\?\w|\?\w", text))


def _normalize_term(term: str) -> str:
    return TextNormalizer.normalize_for_comparison(term).strip("()\"'")
