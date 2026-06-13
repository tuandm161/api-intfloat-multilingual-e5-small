"""Deterministic mock paraphrase generator."""

from app.modules.paraphrase.providers.base import GenerateRequest


class MockParaphraseGenerator:
    Q001_CANDIDATES = [
        "Mục tiêu chính của việc ưu tiên Airway - Breathing - Circulation trong chăm sóc cấp tính là gì?",
        "Trong tình huống cấp cứu, vì sao nhân viên y tế cần ưu tiên đánh giá ABC?",
        "Việc áp dụng nguyên tắc ABC trong chăm sóc cấp tính chủ yếu nhằm đảm bảo điều gì?",
        "ABC trong chăm sóc cấp tính giúp phân loại người bệnh để chuyển khoa nhanh hơn đúng không?",
        "Khi chăm sóc cấp tính, ưu tiên ABC có mục đích làm giảm lo âu cho gia đình người bệnh phải không?",
    ]

    def generate_stem_paraphrases(self, request: GenerateRequest) -> list[str]:
        if request.source.id == "Q001":
            candidates = self.Q001_CANDIDATES
        else:
            stem = request.source.stem.rstrip(" ?")
            candidates = [
                f"Mục tiêu chính được đề cập trong câu hỏi sau là gì: {stem}?",
                f"Trong thực hành điều dưỡng, cần hiểu như thế nào về vấn đề: {stem}?",
                f"{request.source.stem}",
                f"Nội dung nào mô tả đúng nhất vấn đề sau: {stem}?",
                f"Khi chăm sóc người bệnh, câu hỏi nào cần được trả lời về: {stem}?",
            ]
        return candidates[: request.requested_count]
