"""Old gold maths. Pure functions with no database access.

Money is stored as integer paise. The rate is paise per gram of fine gold.
"""
import re

# Assumption A-22: the brief gives no figure for "high-value".
HIGH_VALUE_PAISE = 20_000_000  # Rs 2,00,000
MAX_RATE_PAISE = 10_000_000  # Rs 1,00,000 per gram, a typo guard

PAN_RE = re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]")
_RUPEES_RE = re.compile(r"[0-9]{1,7}(?:\.[0-9]{1,2})?")


def parse_rupees(text) -> int:
    """Parse rupees with up to 2 decimals into integer paise."""
    if not isinstance(text, str):
        raise TypeError("Amount must be given as text")
    cleaned = text.strip()
    if not _RUPEES_RE.fullmatch(cleaned):
        raise ValueError("Amount is not valid")
    whole, _, fraction = cleaned.partition(".")
    return int(whole) * 100 + int(fraction.ljust(2, "0"))


def format_rupees(paise: int) -> str:
    """Format paise as rupees with exactly 2 decimals, for example 25878750 gives 258787.50."""
    if isinstance(paise, bool) or not isinstance(paise, int):
        raise TypeError("Amount must be an integer")
    sign = "-" if paise < 0 else ""
    magnitude = abs(paise)
    return f"{sign}{magnitude // 100}.{magnitude % 100:02d}"


def value_paise(fine_mg: int, rate_paise_per_g: int) -> int:
    """Value of fine gold in paise: milligrams x paise per gram / 1000, half up."""
    for value, label in ((fine_mg, "Fine weight"), (rate_paise_per_g, "Rate")):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{label} must be an integer")
        if value < 0:
            raise ValueError(f"{label} cannot be negative")
    return (fine_mg * rate_paise_per_g + 500) // 1000


def is_high_value(value: int) -> bool:
    return value >= HIGH_VALUE_PAISE


def mask_pan(pan: str) -> str:
    """Hide the first six characters, for example ABCDE1234F becomes XXXXXX234F."""
    return "X" * 6 + pan[6:]