from app.modules.validation.lexical import calculate_lexical_difference
from app.modules.validation.rules import changed_to_true_false


def test_lexical_difference_is_zero_for_same_tokens() -> None:
    assert calculate_lexical_difference("ABC chăm sóc", "abc chăm sóc") == 0.0


def test_true_false_format_rule_supports_vietnamese() -> None:
    assert changed_to_true_false("Đây là mục đích của ABC phải không?")
