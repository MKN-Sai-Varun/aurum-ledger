import pytest

from app.domain.gold_math import (
    allowed_wastage_mg,
    fine_weight_mg,
    format_pct,
    format_weight_g,
    parse_purity_pct,
    parse_wastage_pct,
    parse_weight_g,
)

# Sample ledger from the client brief (Murugesan S):
#   TX-30411 Issue            120.000 g @ 91.60 -> fine 109.920, balance 109.920
#   TX-30437 Receipt, neckl.  112.450 g @ 91.60 -> fine 103.004, balance 6.916
#   TX-30438 Receipt, scrap     3.300 g @ 91.60 -> fine   3.023, balance 3.893
PURITY = parse_purity_pct("91.60")


def test_sample_issue_fine_weight():
    gross = parse_weight_g("120.000")
    assert format_weight_g(fine_weight_mg(gross, PURITY)) == "109.920"


def test_sample_necklace_fine_weight():
    gross = parse_weight_g("112.450")
    assert format_weight_g(fine_weight_mg(gross, PURITY)) == "103.004"


def test_sample_scrap_fine_weight():
    gross = parse_weight_g("3.300")
    assert format_weight_g(fine_weight_mg(gross, PURITY)) == "3.023"


def test_sample_running_balances():
    issued = fine_weight_mg(parse_weight_g("120.000"), PURITY)
    necklace = fine_weight_mg(parse_weight_g("112.450"), PURITY)
    scrap = fine_weight_mg(parse_weight_g("3.300"), PURITY)
    after_necklace = issued - necklace
    after_scrap = after_necklace - scrap
    assert format_weight_g(after_necklace) == "6.916"
    assert format_weight_g(after_scrap) == "3.893"


def test_allowed_wastage_is_three_percent_of_fine_issued():
    # Assumption D-001: allowed wastage = percentage x fine gold issued.
    issued = fine_weight_mg(parse_weight_g("120.000"), PURITY)
    allowed = allowed_wastage_mg(issued, parse_wastage_pct("3.00"))
    assert format_weight_g(allowed) == "3.298"
    remaining = 3893 - allowed
    assert format_weight_g(remaining) == "0.595"


def test_rounds_half_up():
    # 1 mg at 50.00 percent is exactly 0.5 mg, which rounds up to 1.
    assert fine_weight_mg(1, 5000) == 1
    # 1 mg at 49.99 percent is below 0.5 mg, which rounds down to 0.
    assert fine_weight_mg(1, 4999) == 0


def test_zero_gross_gives_zero_fine():
    assert fine_weight_mg(0, PURITY) == 0


@pytest.mark.parametrize(
    "text, expected",
    [("112.450", 112450), ("120", 120000), ("0.001", 1), ("3.3", 3300), (" 7.5 ", 7500)],
)
def test_parse_weight_valid(text, expected):
    assert parse_weight_g(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "abc", "-1", "1.2345", "1e3", "NaN", "1,5", ".5", "1.", "1234567", "٣.٠٠٠"],
)
def test_parse_weight_invalid(text):
    with pytest.raises(ValueError):
        parse_weight_g(text)


def test_parse_weight_rejects_float_input():
    with pytest.raises(TypeError):
        parse_weight_g(112.45)


@pytest.mark.parametrize(
    "text, expected",
    [("91.60", 9160), ("100", 10000), ("75.5", 7550), ("0.01", 1)],
)
def test_parse_purity_valid(text, expected):
    assert parse_purity_pct(text) == expected


@pytest.mark.parametrize("text", ["", "100.01", "91.605", "-5", "abc", "0", "1000"])
def test_parse_purity_invalid(text):
    with pytest.raises(ValueError):
        parse_purity_pct(text)


def test_parse_wastage_accepts_zero():
    assert parse_wastage_pct("0") == 0
    assert parse_wastage_pct("3.00") == 300


def test_parse_wastage_rejects_over_100():
    with pytest.raises(ValueError):
        parse_wastage_pct("100.01")


@pytest.mark.parametrize(
    "mg, expected",
    [(112450, "112.450"), (1, "0.001"), (0, "0.000"), (-595, "-0.595")],
)
def test_format_weight(mg, expected):
    assert format_weight_g(mg) == expected


@pytest.mark.parametrize("hundredths, expected", [(9160, "91.60"), (5, "0.05")])
def test_format_pct(hundredths, expected):
    assert format_pct(hundredths) == expected


def test_fine_weight_rejects_negative_gross():
    with pytest.raises(ValueError):
        fine_weight_mg(-1, PURITY)


def test_fine_weight_rejects_purity_over_100():
    with pytest.raises(ValueError):
        fine_weight_mg(1000, 10001)


def test_fine_weight_rejects_booleans_and_floats():
    with pytest.raises(TypeError):
        fine_weight_mg(True, PURITY)
    with pytest.raises(TypeError):
        fine_weight_mg(1000.5, PURITY)