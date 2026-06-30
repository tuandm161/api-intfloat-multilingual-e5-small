"""Shared Jinja templates and Vietnamese display labels."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

DISPLAY_LABELS = {
    "APPROVED": "Đã duyệt",
    "ARCHIVED": "Đã lưu trữ",
    "CREATED": "Đã tạo",
    "DRAFT": "Bản nháp",
    "FAILED": "Thất bại",
    "GENERATED": "Đã tạo",
    "GENERATING": "Đang tạo",
    "GOOD": "Đạt",
    "NEED_REVIEW": "Cần xem xét",
    "ORIGINAL": "Câu gốc",
    "PARAPHRASE": "Câu diễn đạt lại",
    "REJECTED": "Đã từ chối",
    "SAVED": "Đã lưu",
    "VALIDATED": "Đã kiểm định",
    "VALIDATING": "Đang kiểm định",
    "COMPLETED": "Hoàn tất",
    "READY": "Sẵn sàng",
    "OCR_REQUIRED": "Cần OCR",
    "basic": "Cơ bản",
    "intermediate": "Trung bình",
    "advanced": "Nâng cao",
    "vi": "Tiếng Việt",
    "en": "Tiếng Anh",
    "bilingual": "Song ngữ",
    "light": "Nhẹ",
    "medium": "Vừa",
    "strong": "Mạnh",
    "mock": "Mô phỏng",
    "api": "API",
    "local": "Cục bộ",
}

WARNING_LABELS = {
    "SEMANTIC_DRIFT": "Nội dung có dấu hiệu lệch nghĩa so với câu gốc.",
    "SEMANTIC_UNCERTAIN": "Mức độ tương đồng ngữ nghĩa chưa đủ chắc chắn.",
    "TOO_SIMILAR_TO_SOURCE": "Câu mới quá giống câu gốc.",
    "TOO_LITTLE_REWRITE": "Mức độ diễn đạt lại còn quá ít.",
    "POSSIBLE_DUPLICATE_WITH_EXISTING_QUESTION": "Có thể trùng với một câu hỏi hiện có.",
    "STRONG_DUPLICATE_WITH_EXISTING_QUESTION": "Khả năng cao trùng với một câu hỏi hiện có.",
    "CONTAINS_ANSWER_HINT": "Câu hỏi có thể chứa gợi ý về đáp án.",
    "FORMAT_CHANGED_TO_TRUE_FALSE": "Định dạng đã bị đổi thành câu hỏi đúng/sai.",
    "EMPTY_OR_TOO_SHORT": "Nội dung trống hoặc quá ngắn.",
    "TOO_LONG": "Nội dung quá dài.",
    "VECTOR_INDEX_NOT_READY": "Chỉ mục tìm kiếm tương đồng chưa sẵn sàng.",
    "EDITED_REVALIDATION_REQUIRED": "Câu đã được chỉnh sửa và cần kiểm định lại.",
    "DOCUMENT_SCHEMA_INVALID": "Câu hỏi do tài liệu sinh ra thiếu trường bắt buộc hoặc sai đáp án.",
    "SOURCE_EXCERPT_MISSING": "Thiếu trích dẫn nguồn từ tài liệu.",
    "SOURCE_EXCERPT_NOT_FOUND": "Trích dẫn nguồn không khớp rõ với chunk tài liệu.",
    "DUPLICATE_WITH_DOCUMENT_CANDIDATE": "Có thể trùng với một câu hỏi đề xuất khác trong cùng phiên.",
    "DOCUMENT_OPTION_DUPLICATE": "Các phương án trả lời bị trùng nhau.",
    "DOCUMENT_OPTION_INVALID_PATTERN": "Phương án trả lời dùng mẫu không phù hợp như 'tất cả đều đúng' hoặc gộp nhiều đáp án.",
    "DOCUMENT_LLM_NOT_ANSWERABLE": "Bộ kiểm định AI đánh giá câu hỏi chưa trả lời được từ nguồn.",
    "DOCUMENT_LLM_MULTIPLE_ANSWERS": "Bộ kiểm định AI đánh giá có thể có nhiều hơn một đáp án đúng.",
    "DOCUMENT_LLM_CORRECT_ANSWER_UNSUPPORTED": "Bộ kiểm định AI đánh giá đáp án đúng chưa được nguồn hỗ trợ rõ.",
    "DOCUMENT_LLM_LOW_QUALITY": "Bộ kiểm định AI đánh giá chất lượng câu hỏi thấp.",
    "DOCUMENT_LLM_VALIDATION_FAILED": "Không chạy được bước kiểm định AI bổ sung.",
}

ERROR_LABELS = {
    "API generation provider is not configured": "Nhà cung cấp tạo câu qua API chưa được cấu hình",
    "Local generation provider is not configured": "Nhà cung cấp mô hình cục bộ chưa được cấu hình",
    "Paraphrase generation failed": "Không thể tạo câu diễn đạt lại",
}


def display_label(value: object) -> str:
    if value is None:
        return "-"
    text = str(value)
    return DISPLAY_LABELS.get(text, text)


def warning_label(value: object) -> str:
    text = str(value)
    return WARNING_LABELS.get(text, text)


def error_label(value: object) -> str:
    text = str(value)
    return ERROR_LABELS.get(text, text)


templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)
templates.env.filters["vi_label"] = display_label
templates.env.filters["vi_warning"] = warning_label
templates.env.filters["vi_error"] = error_label
