import pytest

from app.domain.old_gold_math import (
    HIGH_VALUE_PAISE,
    PAN_RE,
    format_rupees,
    is_high_value,
    mask_pan,
    parse_rupees,
    value_paise,
)


@pytest.mark.parametrize(
    "text, expected",
    [("12500", 1_250_000), ("12500.00", 1_250_000), ("0.5", 50), ("0.01", 1), (" 99.9 ", 9990)],
)
def test_parse_rupees_valid(text, expected):
    assert parse_rupees(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "-1", "1.234", "1e3", ".5", "1.", "12345678", "1,000"])
def test_parse_rupees_invalid(text):
    with pytest.raises(ValueError):
        parse_rupees(text)


def test_parse_rupees_rejects_numbers():
    with pytest.raises(TypeError):
        parse_rupees(12.5)


@pytest.mark.parametrize(
    "paise, text",
    [(25_878_750, "258787.50"), (0, "0.00"), (5, "0.05"), (-250, "-2.50")],
)
def test_format_rupees(paise, text):
    assert format_rupees(paise) == text


def test_value_is_milligrams_times_rate_over_a_thousand():
    assert value_paise(20_703, 1_250_000) == 25_878_750
    assert value_paise(6_232, 1_250_000) == 7_790_000
    assert value_paise(46_487, 1_250_000) == 58_108_750


def test_value_rounds_half_up():
    assert value_paise(1, 500) == 1
    assert value_paise(1, 499) == 0
    assert value_paise(0, 1_250_000) == 0


def test_value_rejects_bad_input():
    with pytest.raises(ValueError):
        value_paise(-1, 100)
    with pytest.raises(TypeError):
        value_paise(1.5, 100)


def test_high_value_boundary():
    assert is_high_value(HIGH_VALUE_PAISE) is True
    assert is_high_value(HIGH_VALUE_PAISE - 1) is False


def test_mask_pan_hides_the_first_six():
    assert mask_pan("ABCDE1234F") == "XXXXXX234F"


@pytest.mark.parametrize("pan", ["ABCDE1234F", "AAAPL1234C"])
def test_valid_pans(pan):
    assert PAN_RE.fullmatch(pan)


@pytest.mark.parametrize("pan", ["abcde1234f", "ABCDE12345", "1234567890", "ABCD1234FG", "ABCDE1234", ""])
def test_invalid_pans(pan):
    assert PAN_RE.fullmatch(pan) is None