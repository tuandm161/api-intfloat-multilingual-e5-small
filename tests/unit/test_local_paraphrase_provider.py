from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.enums import ErrorCode
from app.core.errors import AppError
from app.modules.paraphrase.providers.base import GenerateRequest, GeneratedParaphrase
from app.modules.paraphrase.providers.local import (
    LocalParaphraseGenerator,
    _protected_terms_by_field,
    extract_protected_terms,
    missing_protected_terms,
)


class FakeLlama:
    def __init__(self, content: str | list[str]) -> None:
        self.contents = [content] if isinstance(content, str) else content
        self.calls = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self.contents) - 1)
        return {"choices": [{"message": {"content": self.contents[index]}}]}


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


def make_vitals_request() -> GenerateRequest:
    return GenerateRequest(
        source=SimpleNamespace(
            stem="Khi SpO2 < 90% và HA 80 mmHg, ưu tiên can thiệp ABC nào?",
            option_a="Hỗ trợ đường thở và thở oxy.",
            option_b="Ghi hồ sơ sau khi hết ca.",
            option_c="Cho người bệnh uống nước.",
            option_d="Chuyển sang giáo dục sức khỏe.",
            correct_answer="A",
        ),
        requested_count=2,
        target_language="vi",
        change_strength="medium",
    )


def full_candidate(
    stem: str,
    *,
    option_a: str = "Làm đủ các bước kỹ thuật theo thời gian yêu cầu.",
    option_b: str = "Duy trì sự sống của người bệnh trong giai đoạn cấp cứu.",
    option_c: str = "Giúp người nhà người bệnh bớt lo lắng.",
    option_d: str = "Phân nhóm người bệnh để chuyển khoa sớm hơn.",
) -> str:
    return (
        '{"stem":"'
        + stem
        + '","optionA":"'
        + option_a
        + '","optionB":"'
        + option_b
        + '","optionC":"'
        + option_c
        + '","optionD":"'
        + option_d
        + '"}'
    )


def candidate_outputs(
    stem: str,
    *,
    option_a: str = "Làm đủ các bước kỹ thuật theo thời gian yêu cầu.",
    option_b: str = "Duy trì sự sống của người bệnh trong giai đoạn cấp cứu.",
    option_c: str = "Giúp người nhà người bệnh bớt lo lắng.",
    option_d: str = "Phân nhóm người bệnh để chuyển khoa sớm hơn.",
) -> list[str]:
    return [stem, option_a, option_b, option_c, option_d]


def vitals_candidate(
    stem: str,
    *,
    option_a: str = "Ưu tiên hỗ trợ đường thở và cho thở oxy.",
    option_b: str = "Hoàn tất ghi chép hồ sơ vào cuối ca.",
    option_c: str = "Cho người bệnh uống thêm nước.",
    option_d: str = "Chuyển sang tư vấn giáo dục sức khỏe.",
) -> str:
    return (
        '{"stem":"'
        + stem
        + '","optionA":"'
        + option_a
        + '","optionB":"'
        + option_b
        + '","optionC":"'
        + option_c
        + '","optionD":"'
        + option_d
        + '"}'
    )


def test_local_generator_uses_chat_completion_and_parses_json() -> None:
    model = FakeLlama(
        candidate_outputs("Vì sao cần ưu tiên đánh giá ABC trước trong chăm sóc cấp tính?")
        + candidate_outputs("Khi chăm sóc cấp tính, ABC cần được ưu tiên vì lý do gì?")
    )
    settings = Settings(_env_file=None, local_paraphrase_temperature=0.2)

    candidates = LocalParaphraseGenerator(settings, model=model).generate_paraphrases(
        make_request()
    )

    assert [item.stem for item in candidates] == [
        "Vì sao cần ưu tiên đánh giá ABC trước trong chăm sóc cấp tính?",
        "Khi chăm sóc cấp tính, ABC cần được ưu tiên vì lý do gì?",
    ]
    assert candidates[0].option_b == "Duy trì sự sống của người bệnh trong giai đoạn cấp cứu."
    call = model.calls[0]
    assert call["temperature"] == 0.2
    assert call["max_tokens"] == min(settings.local_paraphrase_max_tokens, 256)
    assert call["messages"][0]["role"] == "system"
    prompt = call["messages"][1]["content"]
    assert "Chỉ trả về đúng một dòng" in prompt
    assert "ABC" in prompt
    assert "QUESTION_STEM nguồn:" in prompt
    assert "OPTION_A nguồn:" not in prompt
    assert "Hoàn thành quy trình kỹ thuật đúng thời gian" in prompt
    assert "Đảm bảo sự sống còn của người bệnh" in prompt
    option_prompt = model.calls[1]["messages"][1]["content"]
    assert "OPTION_A nguồn:" in option_prompt
    assert "STEM đã viết lại" in option_prompt


def test_local_field_parser_cleans_labels_quotes_and_json() -> None:
    assert LocalParaphraseGenerator._parse_field_text(
        '{"text":"OPTION_A: Đáp án đã viết lại."}', "optionA"
    ) == "Đáp án đã viết lại."
    assert LocalParaphraseGenerator._parse_field_text(
        "```text\nQUESTION_STEM: Câu hỏi đã viết lại?\n```", "stem"
    ) == "Câu hỏi đã viết lại?"


def test_local_parser_extracts_json_from_surrounding_text() -> None:
    candidates = LocalParaphraseGenerator._parse_candidates(
        '```json\n{"candidates":['
        + full_candidate("Câu hỏi mới là gì?")
        + "]}\n```",
        requested_count=3,
    )

    assert [item.stem for item in candidates] == ["Câu hỏi mới là gì?"]
    assert candidates[0].option_a


def test_local_parser_requires_candidates_list() -> None:
    with pytest.raises(AppError) as exc_info:
        LocalParaphraseGenerator._parse_candidates('{"items":[]}', requested_count=3)

    assert exc_info.value.code is ErrorCode.GENERATION_FAILED
    assert exc_info.value.status_code == 503


def test_local_parser_rejects_empty_candidates() -> None:
    with pytest.raises(AppError) as exc_info:
        LocalParaphraseGenerator._parse_candidates(
            '{"candidates":[{"stem":"Câu hỏi thiếu option?"},{}]}',
            requested_count=3,
        )

    assert exc_info.value.code is ErrorCode.GENERATION_FAILED
    assert exc_info.value.status_code == 503


def test_protected_terms_are_extracted_and_checked_case_insensitively() -> None:
    terms = extract_protected_terms(
        'Đánh giá (Primary Survey) khi SpO2 < 90% và HA 80 mmHg theo ABC?'
    )

    assert "Primary Survey" in terms
    assert "SpO2" in terms
    assert "< 90%" in terms
    assert "80 mmHg" in terms
    assert "ABC" in terms
    assert missing_protected_terms(
        "Trong primary survey, SpO2 < 90% và HA 80 mmHg cần ưu tiên ABC nào?",
        terms,
    ) == []


def test_local_generator_filters_source_duplicates_candidate_duplicates_and_missing_terms() -> None:
    model = FakeLlama(
        candidate_outputs(
            "Khi SpO2 < 90% và HA 80 mmHg, ưu tiên can thiệp ABC nào?",
            option_a="Ưu tiên hỗ trợ đường thở và cho thở oxy.",
            option_b="Hoàn tất ghi chép hồ sơ vào cuối ca.",
            option_c="Cho người bệnh uống thêm nước.",
            option_d="Chuyển sang tư vấn giáo dục sức khỏe.",
        )
        + candidate_outputs(
            "Trong tình huống SpO2 < 90% và HA 80 mmHg, điều dưỡng nên ưu tiên ABC thế nào?",
            option_a="Ưu tiên hỗ trợ đường thở và cho thở oxy.",
            option_b="Hoàn tất ghi chép hồ sơ vào cuối ca.",
            option_c="Cho người bệnh uống thêm nước.",
            option_d="Chuyển sang tư vấn giáo dục sức khỏe.",
        )
        + candidate_outputs(
            "Trong tình huống SpO2 < 90% và HA 80 mmHg, điều dưỡng nên ưu tiên ABC thế nào?",
            option_a="Ưu tiên hỗ trợ đường thở và cho thở oxy.",
            option_b="Hoàn tất ghi chép hồ sơ vào cuối ca.",
            option_c="Cho người bệnh uống thêm nước.",
            option_d="Chuyển sang tư vấn giáo dục sức khỏe.",
        )
        + candidate_outputs(
            "Điều dưỡng cần xử trí ưu tiên ABC ra sao khi SpO2 < 90% và HA 80 mmHg?",
            option_a="Ưu tiên hỗ trợ đường thở và cho thở oxy.",
            option_b="Hoàn tất ghi chép hồ sơ vào cuối ca.",
            option_c="Cho người bệnh uống thêm nước.",
            option_d="Chuyển sang tư vấn giáo dục sức khỏe.",
        )
    )

    candidates = LocalParaphraseGenerator(
        Settings(_env_file=None), model=model
    ).generate_paraphrases(make_vitals_request())

    assert [item.stem for item in candidates] == [
        "Trong tình huống SpO2 < 90% và HA 80 mmHg, điều dưỡng nên ưu tiên ABC thế nào?",
        "Điều dưỡng cần xử trí ưu tiên ABC ra sao khi SpO2 < 90% và HA 80 mmHg?",
    ]
    assert candidates[0].option_a == "Ưu tiên hỗ trợ đường thở và cho thở oxy."


def test_local_filter_drops_duplicate_candidates_and_answer_hints() -> None:
    request = make_request()
    protected_terms = _protected_terms_by_field(request.source)

    filtered, stats = LocalParaphraseGenerator._filter_candidates(
        request,
        [
            GeneratedParaphrase(
                "Vì sao cần ưu tiên đánh giá ABC trong chăm sóc cấp tính?",
                "Làm đủ các bước kỹ thuật theo thời gian yêu cầu.",
                "Duy trì sự sống của người bệnh trong giai đoạn cấp cứu.",
                "Giúp người nhà người bệnh bớt lo lắng.",
                "Phân nhóm người bệnh để chuyển khoa sớm hơn.",
            ),
            GeneratedParaphrase(
                "Vì sao cần ưu tiên đánh giá ABC trong chăm sóc cấp tính?",
                "Làm đủ các bước kỹ thuật theo thời gian yêu cầu.",
                "Duy trì sự sống của người bệnh trong giai đoạn cấp cứu.",
                "Giúp người nhà người bệnh bớt lo lắng.",
                "Phân nhóm người bệnh để chuyển khoa sớm hơn.",
            ),
            GeneratedParaphrase(
                "Mục tiêu của ưu tiên ABC trong chăm sóc cấp tính là gì?",
                "Hoàn tất thao tác kỹ thuật đúng thời lượng.",
                "Bảo toàn các chức năng sống thiết yếu của người bệnh.",
                "Trấn an thân nhân của người bệnh.",
                "Sắp xếp người bệnh để chuyển khoa nhanh.",
            ),
            GeneratedParaphrase(
                "Ưu tiên ABC nhằm đảm bảo sự sống còn của người bệnh trong cấp tính đúng không?",
                "Hoàn tất thao tác kỹ thuật đúng thời lượng.",
                "Bảo toàn các chức năng sống thiết yếu của người bệnh.",
                "Trấn an thân nhân của người bệnh.",
                "Sắp xếp người bệnh để chuyển khoa nhanh.",
            ),
        ],
        protected_terms,
    )

    assert [item.stem for item in filtered] == [
        "Vì sao cần ưu tiên đánh giá ABC trong chăm sóc cấp tính?",
        "Mục tiêu của ưu tiên ABC trong chăm sóc cấp tính là gì?",
    ]
    assert stats["candidate_duplicate"] == 1
    assert stats["answer_hint"] == 1


def test_local_filter_drops_nearly_copied_source() -> None:
    request = GenerateRequest(
        source=SimpleNamespace(
            stem="Trong chăm sóc cấp tính, việc ưu tiên nhu cầu ABC nhằm mục đích gì?",
            option_a="Hoàn thành quy trình kỹ thuật đúng thời gian.",
            option_b="Đảm bảo sự sống còn của người bệnh.",
            option_c="Giảm lo âu cho gia đình người bệnh.",
            option_d="Phân loại bệnh nhân để chuyển khoa nhanh chóng.",
            correct_answer="B",
        ),
        requested_count=1,
        target_language="vi",
        change_strength="medium",
    )
    protected_terms = _protected_terms_by_field(request.source)

    filtered, stats = LocalParaphraseGenerator._filter_candidates(
        request,
        [
            GeneratedParaphrase(
                "Trong chăm sóc cấp tính, việc ưu tiên ABC nhằm mục đích gì?",
                "Làm đủ các bước kỹ thuật theo thời gian yêu cầu.",
                "Duy trì sự sống của người bệnh trong giai đoạn cấp cứu.",
                "Giúp người nhà người bệnh bớt lo lắng.",
                "Phân nhóm người bệnh để chuyển khoa sớm hơn.",
            ),
            GeneratedParaphrase(
                "Mục tiêu của ưu tiên ABC trong chăm sóc cấp tính là gì?",
                "Làm đủ các bước kỹ thuật theo thời gian yêu cầu.",
                "Duy trì sự sống của người bệnh trong giai đoạn cấp cứu.",
                "Giúp người nhà người bệnh bớt lo lắng.",
                "Phân nhóm người bệnh để chuyển khoa sớm hơn.",
            ),
        ],
        protected_terms,
    )

    assert [item.stem for item in filtered] == [
        "Mục tiêu của ưu tiên ABC trong chăm sóc cấp tính là gì?"
    ]
    assert stats["too_similar"] == 1


def test_local_filter_drops_corrupted_text_and_option_specific_terms() -> None:
    request = GenerateRequest(
        source=SimpleNamespace(
            stem="Nếu SpO2 giảm dưới 92% hoặc huyết áp tâm thu dưới 90 mmHg, dấu hiệu nào cần ưu tiên?",
            option_a="SpO2 98%, huyết áp 120/80 mmHg",
            option_b="SpO2 91%, huyết áp tâm thu 88 mmHg",
            option_c="Nhiệt độ 36,8 độ C",
            option_d="Mạch 78 lần/phút",
            correct_answer="B",
        ),
        requested_count=1,
        target_language="vi",
        change_strength="medium",
    )
    protected_terms = _protected_terms_by_field(request.source)

    filtered, stats = LocalParaphraseGenerator._filter_candidates(
        request,
        [
            GeneratedParaphrase(
                "N?u SpO2 gi?m d??i 92% ho?c huy?t áp tâm thu dưới 90 mmHg thì ưu tiên gì?",
                "SpO2 98%, huyết áp 120/80 mmHg ổn định.",
                "SpO2 91%, huyết áp tâm thu 88 mmHg bất thường.",
                "Thân nhiệt 36,8 độ C.",
                "Mạch 78 lần/phút.",
            ),
            GeneratedParaphrase(
                "Khi SpO2 giảm dưới 92% hoặc huyết áp tâm thu dưới 90 mmHg, SpO2 91% và 88 mmHg gợi ý điều gì?",
                "SpO2 98%, huyết áp 120/80 mmHg ổn định.",
                "SpO2 91%, huyết áp tâm thu 88 mmHg bất thường.",
                "Thân nhiệt 36,8 độ C.",
                "Mạch 78 lần/phút.",
            ),
            GeneratedParaphrase(
                "Khi SpO2 giảm dưới 92% hoặc huyết áp tâm thu dưới 90 mmHg, điều dưỡng cần ưu tiên đánh giá dấu hiệu nào?",
                "SpO2 98%, huyết áp 120/80 mmHg trong giới hạn.",
                "SpO2 91%, huyết áp tâm thu 88 mmHg cần chú ý.",
                "Nhiệt độ cơ thể 36,8 độ C.",
                "Tần số mạch 78 lần/phút.",
            ),
        ],
        protected_terms,
    )

    assert [item.stem for item in filtered] == [
        "Khi SpO2 giảm dưới 92% hoặc huyết áp tâm thu dưới 90 mmHg, điều dưỡng cần ưu tiên đánh giá dấu hiệu nào?"
    ]
    assert stats["corrupted_text"] == 1
    assert stats["answer_hint"] == 1


def test_local_generator_retries_once_when_required_terms_are_missing() -> None:
    model = FakeLlama(
        candidate_outputs(
            "Khi độ bão hòa oxy giảm, cần ưu tiên gì?",
            option_a="Ưu tiên hỗ trợ đường thở và cho thở oxy.",
            option_b="Hoàn tất ghi chép hồ sơ vào cuối ca.",
            option_c="Cho người bệnh uống thêm nước.",
            option_d="Chuyển sang tư vấn giáo dục sức khỏe.",
        )
        + candidate_outputs(
            "Trong tình huống SpO2 < 90% và HA 80 mmHg, điều dưỡng nên ưu tiên ABC thế nào?",
            option_a="Ưu tiên hỗ trợ đường thở và cho thở oxy.",
            option_b="Hoàn tất ghi chép hồ sơ vào cuối ca.",
            option_c="Cho người bệnh uống thêm nước.",
            option_d="Chuyển sang tư vấn giáo dục sức khỏe.",
        )
        + candidate_outputs(
            "Điều dưỡng cần xử trí ưu tiên ABC ra sao khi SpO2 < 90% và HA 80 mmHg?",
            option_a="Ưu tiên hỗ trợ đường thở và cho thở oxy.",
            option_b="Hoàn tất ghi chép hồ sơ vào cuối ca.",
            option_c="Cho người bệnh uống thêm nước.",
            option_d="Chuyển sang tư vấn giáo dục sức khỏe.",
        )
    )

    candidates = LocalParaphraseGenerator(
        Settings(_env_file=None), model=model
    ).generate_paraphrases(make_vitals_request())

    assert [item.stem for item in candidates] == [
        "Trong tình huống SpO2 < 90% và HA 80 mmHg, điều dưỡng nên ưu tiên ABC thế nào?",
        "Điều dưỡng cần xử trí ưu tiên ABC ra sao khi SpO2 < 90% và HA 80 mmHg?",
    ]
    assert len(model.calls) == 15
    retry_prompt = model.calls[5]["messages"][1]["content"]
    assert "Lần trước bị loại vì:" in retry_prompt
    assert "SpO2" in retry_prompt


def test_local_generator_rejects_empty_field_after_retry_budget() -> None:
    model = FakeLlama([""])

    with pytest.raises(AppError) as exc_info:
        LocalParaphraseGenerator(
            Settings(_env_file=None), model=model
        ).generate_paraphrases(make_request())

    assert len(model.calls) == 6
    assert exc_info.value.code is ErrorCode.GENERATION_FAILED
    assert exc_info.value.status_code == 503


def test_local_generator_fails_when_no_candidate_survives_after_retry() -> None:
    model = FakeLlama(
        candidate_outputs(
            "Khi độ bão hòa oxy giảm, cần ưu tiên gì?",
            option_a="Ưu tiên hỗ trợ đường thở và cho thở oxy.",
            option_b="Hoàn tất ghi chép hồ sơ vào cuối ca.",
            option_c="Cho người bệnh uống thêm nước.",
            option_d="Chuyển sang tư vấn giáo dục sức khỏe.",
        )
    )

    with pytest.raises(AppError) as exc_info:
        LocalParaphraseGenerator(
            Settings(_env_file=None), model=model
        ).generate_paraphrases(make_vitals_request())

    assert len(model.calls) == 30
    assert exc_info.value.code is ErrorCode.GENERATION_FAILED
    assert "not_enough_valid_candidates: 0/2" in exc_info.value.details["reason"]
    assert "missing_required_terms" in exc_info.value.details["reason"]
