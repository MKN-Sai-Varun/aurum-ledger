"""Day-closing maths. Pure functions with no database access."""


def _require_int(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")


def difference_mg(counted_mg: int, expected_mg: int) -> int:
    """Counted minus expected. Negative means less gold was counted than the records show."""
    _require_int(counted_mg, "Counted")
    _require_int(expected_mg, "Expected")
    return counted_mg - expected_mg


def reconciles(opening_vault_mg: int, effects: list[int], closing_vault_mg: int) -> bool:
    """The opening vault plus every movement's effect must equal the closing vault."""
    _require_int(opening_vault_mg, "Opening")
    _require_int(closing_vault_mg, "Closing")
    for effect in effects:
        _require_int(effect, "Effect")
    return opening_vault_mg + sum(effects) == closing_vault_mg