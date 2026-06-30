from app.modules.validation.lexical import calculate_lexical_difference
from app.modules.validation.rules import changed_to_true_false, contains_option_content


def test_lexical_difference_is_zero_for_same_tokens() -> None:
    assert calculate_lexical_difference("ABC chăm sóc", "abc chăm sóc") == 0.0


def test_true_false_format_rule_supports_vietnamese() -> None:
    assert changed_to_true_false("Đây là mục đích của ABC phải không?")


def test_option_content_rule_detects_answer_leakage() -> None:
    source = "Trong chăm sóc cấp tính, việc ưu tiên nhu cầu ABC nhằm mục đích gì?"
    options = (
        "Hoàn thành quy trình kỹ thuật đúng thời gian.",
        "Đảm bảo sự sống còn của người bệnh trong giai đoạn khẩn cấp.",
        "Giảm lo âu cho gia đình người bệnh.",
        "Phân loại bệnh nhân để chuyển khoa nhanh chóng.",
    )

    assert contains_option_content(
        "Ưu tiên ABC nhằm đảm bảo sự sống còn của người bệnh trong cấp tính đúng không?",
        source,
        options,
    )
    assert not contains_option_content(
        "Trong cấp cứu, vì sao cần ưu tiên đánh giá ABC?",
        source,
        options,
    )
