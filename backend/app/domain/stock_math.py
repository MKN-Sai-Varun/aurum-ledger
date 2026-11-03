"""Stock statement maths. Pure functions with no database access.

All gold in the business is either in the vault, with karigars, or at the
refiner, so the vault figure is what remains of the total.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class StockStatement:
    total_mg: int
    vault_mg: int
    karigars_mg: int
    refiner_mg: int

    @property
    def consistent(self) -> bool:
        return self.vault_mg >= 0 and self.refiner_mg >= 0


def compute_statement(
    total_mg: int, sent_mg: int, received_mg: int, karigars_mg: int
) -> StockStatement:
    for value, label in (
        (total_mg, "Total"),
        (sent_mg, "Sent"),
        (received_mg, "Received"),
        (karigars_mg, "Karigars"),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{label} must be an integer")
    refiner = sent_mg - received_mg
    return StockStatement(
        total_mg=total_mg,
        vault_mg=total_mg - karigars_mg - refiner,
        karigars_mg=karigars_mg,
        refiner_mg=refiner,
    )