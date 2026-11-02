"""Exact gold arithmetic.

Weights are stored as integer milligrams. Percentages (purity and
wastage) are stored as integer hundredths of a percent, so 91.60 is
9160. No floating point is used anywhere, so results are exact.

Rounding rule: each line is rounded half-up to the nearest milligram.
"""
import re

MG_PER_G = 1000
PERCENT_SCALE = 10_000
MAX_PERCENT = 10_000  # 100.00 percent

# ASCII digits only. The regex shorthand for digits also matches
# non-ASCII digits, which we do not accept.
_WEIGHT_RE = re.compile(r"[0-9]{1,6}(?:\.[0-9]{1,3})?")
_PERCENT_RE = re.compile(r"[0-9]{1,3}(?:\.[0-9]{1,2})?")


def _parse_scaled(text, pattern, places, label):
    if not isinstance(text, str):
        raise TypeError(f"{label} must be given as text")
    cleaned = text.strip()
    if not pattern.fullmatch(cleaned):
        raise ValueError(f"{label} is not a valid number")
    whole, _, fraction = cleaned.partition(".")
    return int(whole) * 10**places + int(fraction.ljust(places, "0"))


def _require_int(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} cannot be negative")


def parse_weight_g(text: str) -> int:
    """Parse a weight in grams (up to 3 decimals) into integer milligrams."""
    return _parse_scaled(text, _WEIGHT_RE, 3, "Weight")


def _parse_percent(text: str, label: str) -> int:
    value = _parse_scaled(text, _PERCENT_RE, 2, label)
    if value > MAX_PERCENT:
        raise ValueError(f"{label} cannot be more than 100")
    return value


def parse_purity_pct(text: str) -> int:
    """Parse purity (up to 2 decimals, above 0 and up to 100)."""
    value = _parse_percent(text, "Purity")
    if value == 0:
        raise ValueError("Purity must be above 0")
    return value


def parse_wastage_pct(text: str) -> int:
    """Parse an allowed wastage percentage (0 to 100, up to 2 decimals)."""
    return _parse_percent(text, "Wastage")


def _apply_percent(amount_mg: int, percent_hundredths: int) -> int:
    _require_int(amount_mg, "Weight")
    _require_int(percent_hundredths, "Percentage")
    if percent_hundredths > MAX_PERCENT:
        raise ValueError("Percentage cannot be more than 100")
    return (amount_mg * percent_hundredths + PERCENT_SCALE // 2) // PERCENT_SCALE


def fine_weight_mg(gross_mg: int, purity_hundredths: int) -> int:
    """Fine gold in milligrams for a gross weight at a given purity."""
    return _apply_percent(gross_mg, purity_hundredths)


def allowed_wastage_mg(fine_issued_mg: int, wastage_hundredths: int) -> int:
    """Allowed wastage in milligrams: percentage of the fine gold issued."""
    return _apply_percent(fine_issued_mg, wastage_hundredths)


def format_weight_g(mg: int) -> str:
    """Format milligrams as grams with exactly 3 decimals."""
    if isinstance(mg, bool) or not isinstance(mg, int):
        raise TypeError("Weight must be an integer")
    sign = "-" if mg < 0 else ""
    magnitude = abs(mg)
    return f"{sign}{magnitude // MG_PER_G}.{magnitude % MG_PER_G:03d}"


def format_pct(hundredths: int) -> str:
    """Format hundredths of a percent with exactly 2 decimals."""
    if isinstance(hundredths, bool) or not isinstance(hundredths, int):
        raise TypeError("Percentage must be an integer")
    if hundredths < 0:
        raise ValueError("Percentage cannot be negative")
    return f"{hundredths // 100}.{hundredths % 100:02d}"