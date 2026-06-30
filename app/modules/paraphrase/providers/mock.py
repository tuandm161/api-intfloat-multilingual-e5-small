"""Deterministic mock paraphrase generator."""

from app.modules.paraphrase.providers.base import GenerateRequest, GeneratedParaphrase


class MockParaphraseGenerator:
    Q001_CANDIDATES = [
        GeneratedParaphrase(
            stem="Mục tiêu chính của việc ưu tiên Airway - Breathing - Circulation trong chăm sóc cấp tính là gì?",
            option_a="Thực hiện đầy đủ quy trình kỹ thuật trong thời gian quy định.",
            option_b="Bảo đảm duy trì sự sống của người bệnh ở giai đoạn khẩn cấp.",
            option_c="Giúp thân nhân người bệnh bớt lo lắng.",
            option_d="Sàng lọc người bệnh để chuyển khoa sớm hơn.",
        ),
        GeneratedParaphrase(
            stem="Trong tình huống cấp cứu, vì sao nhân viên y tế cần ưu tiên đánh giá ABC?",
            option_a="Để hoàn tất các bước kỹ thuật đúng tiến độ.",
            option_b="Để bảo vệ các chức năng sống còn của người bệnh trong cấp cứu.",
            option_c="Để giảm căng thẳng cho gia đình người bệnh.",
            option_d="Để phân nhóm người bệnh và chuyển khoa nhanh.",
        ),
        GeneratedParaphrase(
            stem="Việc áp dụng nguyên tắc ABC trong chăm sóc cấp tính chủ yếu nhằm đảm bảo điều gì?",
            option_a="Hoàn thành thao tác chuyên môn theo đúng thời lượng.",
            option_b="Duy trì các chức năng sống thiết yếu của người bệnh.",
            option_c="Ổn định tâm lý cho người nhà người bệnh.",
            option_d="Phân loại người bệnh nhằm rút ngắn thời gian chuyển khoa.",
        ),
        GeneratedParaphrase(
            stem="Trong chăm sóc cấp tính, nhân viên y tế cần hiểu nguyên tắc ABC theo hướng nào?",
            option_a="Ưu tiên làm xong quy trình kỹ thuật đúng hạn.",
            option_b="Ưu tiên bảo vệ sự sống còn của người bệnh trong tình huống khẩn.",
            option_c="Ưu tiên trấn an người thân của người bệnh.",
            option_d="Ưu tiên phân luồng người bệnh để chuyển khoa nhanh.",
        ),
        GeneratedParaphrase(
            stem="Khi chăm sóc cấp tính, vì sao nguyên tắc ABC cần được ưu tiên đánh giá trước?",
            option_a="Vì cần hoàn thiện quy trình kỹ thuật theo thời gian yêu cầu.",
            option_b="Vì cần duy trì đường thở, hô hấp và tuần hoàn để bảo toàn sự sống.",
            option_c="Vì cần giúp gia đình người bệnh giảm lo âu.",
            option_d="Vì cần xác định người bệnh để chuyển sang khoa khác nhanh chóng.",
        ),
    ]

    def generate_paraphrases(self, request: GenerateRequest) -> list[GeneratedParaphrase]:
        if request.source.id == "Q001":
            candidates = self.Q001_CANDIDATES
        else:
            stem = request.source.stem.rstrip(" ?")
            candidates = [
                GeneratedParaphrase(
                    stem=f"Câu hỏi này cần được hiểu lại như thế nào: {stem}?",
                    option_a=f"Cách diễn đạt khác của phương án A: {request.source.option_a}",
                    option_b=f"Cách diễn đạt khác của phương án B: {request.source.option_b}",
                    option_c=f"Cách diễn đạt khác của phương án C: {request.source.option_c}",
                    option_d=f"Cách diễn đạt khác của phương án D: {request.source.option_d}",
                ),
                GeneratedParaphrase(
                    stem=f"Trong thực hành điều dưỡng, vấn đề sau nên được hỏi lại ra sao: {stem}?",
                    option_a=f"Phương án A được nêu lại: {request.source.option_a}",
                    option_b=f"Phương án B được nêu lại: {request.source.option_b}",
                    option_c=f"Phương án C được nêu lại: {request.source.option_c}",
                    option_d=f"Phương án D được nêu lại: {request.source.option_d}",
                ),
            ]
        return candidates[: request.requested_count]
