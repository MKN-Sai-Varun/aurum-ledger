"""Turn whatever a reader produced into a valid value, or nothing.

Every reading passes through the same strict parsers as typed values, so an
impossible number is thrown away instead of being shown to the clerk.
"""
import re

from app.domain.gold_math import (
    format_pct,
    format_weight_g,
    parse_purity_pct,
    parse_weight_g,
)
from app.readers.base import PURITY, WEIGHT

MAX_READING_MG = 2_000_000  # 2000.000 g, the same cap as a single issue

_UNIT_TAIL = re.compile(r"\s*(g|gm|gms|grams?|%)$", re.IGNORECASE)
_WEIGHT_CANDIDATE = re.compile(r"(?<![0-9.])[0-9]{1,4}\.[0-9]{1,3}(?![0-9.])")
_PURITY_CANDIDATE = re.compile(r"(?<![0-9.])[0-9]{2,3}\.[0-9]{1,2}(?![0-9.])")


def clean_value(target: str, raw) -> str | None:
    if not isinstance(raw, str):
        return None
    text = _UNIT_TAIL.sub("", raw.strip())
    try:
        if target == WEIGHT:
            mg = parse_weight_g(text)
            if mg <= 0 or mg > MAX_READING_MG:
                return None
            return format_weight_g(mg)
        if target == PURITY:
            return format_pct(parse_purity_pct(text))
    except (ValueError, TypeError):
        return None
    return None


def find_candidates(target: str, text: str) -> list[str]:
    """Pick plausible numbers out of free text, without duplicates."""
    pattern = _WEIGHT_CANDIDATE if target == WEIGHT else _PURITY_CANDIDATE
    found: list[str] = []
    for match in pattern.findall(text or ""):
        value = clean_value(target, match)
        if value is not None and value not in found:
            found.append(value)
    return found