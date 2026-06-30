from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.enums import ErrorCode
from app.core.errors import AppError
from app.modules.paraphrase.providers.base import GenerateRequest
from app.modules.paraphrase.providers.vietquill import VietQuillParaphraseGenerator


class FakeVietQuill:
    def __init__(self, outputs: list[list[str]]) -> None:
        self.outputs = outputs
        self.calls = []

    def paraphrase(self, text: str, **kwargs):
        self.calls.append((text, kwargs))
        index = min(len(self.calls) - 1, len(self.outputs) - 1)
        return self.outputs[index]


def make_request() -> GenerateRequest:
    return GenerateRequest(
        source=SimpleNamespace(
            stem="Trong chăm sóc cấp tính, ưu tiên ABC nhằm mục đích gì?",
            option_a="Hoàn thành quy trình kỹ thuật đúng thời gian.",
            option_b="Đảm bảo sự sống còn của người bệnh.",
            option_c="Giảm lo âu cho gia đình người bệnh.",
            option_d="Phân loại bệnh nhân để chuyển khoa nhanh chóng.",
            correct_answer="B",
        ),
        requested_count=2,
        target_language="vi",
        change_strength="medium",
    )


def test_vietquill_generator_paraphrases_each_field_and_filters() -> None:
    model = FakeVietQuill(
        [
            [
                "Mục tiêu của việc ưu tiên ABC trong chăm sóc cấp tính là gì?",
                "Vì sao cần ưu tiên đánh giá ABC trước trong chăm sóc cấp tính?",
            ],
            [
                "Thực hiện đủ các bước kỹ thuật theo thời gian yêu cầu.",
                "Làm đầy đủ quy trình kỹ thuật trong thời lượng quy định.",
            ],
            [
                "Duy trì sự sống của người bệnh trong giai đoạn cấp cứu.",
                "Bảo vệ các chức năng sống còn của người bệnh.",
            ],
            [
                "Giúp người nhà người bệnh bớt lo lắng.",
                "Làm giảm lo âu cho thân nhân người bệnh.",
            ],
            [
                "Phân nhóm người bệnh để chuyển khoa sớm hơn.",
                "Sàng lọc người bệnh nhằm chuyển khoa nhanh hơn.",
            ],
        ]
    )
    settings = Settings(
        _env_file=None,
        vietquill_style="balanced",
        vietquill_num_beams=4,
        vietquill_max_length=96,
    )

    candidates = VietQuillParaphraseGenerator(settings, model=model).generate_paraphrases(
        make_request()
    )

    assert [item.stem for item in candidates] == [
        "Mục tiêu của việc ưu tiên ABC trong chăm sóc cấp tính là gì?",
        "Vì sao cần ưu tiên đánh giá ABC trước trong chăm sóc cấp tính?",
    ]
    assert candidates[0].option_b == "Duy trì sự sống của người bệnh trong giai đoạn cấp cứu."
    assert len(model.calls) == 5
    assert model.calls[0][1]["style"] == "balanced"
    assert model.calls[0][1]["num_candidates"] == 8
    assert model.calls[0][1]["num_beams"] == 10
    assert model.calls[0][1]["max_length"] == 96


def test_vietquill_generator_fails_when_terms_are_removed() -> None:
    model = FakeVietQuill(
        [
            ["Mục tiêu của việc ưu tiên chăm sóc cấp tính là gì?"],
            ["Thực hiện đủ quy trình kỹ thuật."],
            ["Duy trì sự sống của người bệnh."],
            ["Giúp người nhà bớt lo."],
            ["Phân nhóm người bệnh."],
        ]
    )

    with pytest.raises(AppError) as exc_info:
        VietQuillParaphraseGenerator(
            Settings(_env_file=None), model=model
        ).generate_paraphrases(make_request())

    assert exc_info.value.code is ErrorCode.GENERATION_FAILED
    assert exc_info.value.status_code == 503
    assert "not_enough_valid_candidates" in exc_info.value.details["reason"]
