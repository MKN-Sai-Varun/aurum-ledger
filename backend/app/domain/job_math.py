"""Job-level wastage maths. Pure functions with no database access."""
from dataclasses import dataclass

from app.domain.gold_math import allowed_wastage_mg


@dataclass(frozen=True)
class JobSummary:
    issued_mg: int
    returned_mg: int
    outstanding_mg: int
    wastage_hundredths: int
    allowed_mg: int
    unexplained_mg: int


def summarise_job(
    issued_fine_mg: int, wastage_hundredths: int, outstanding_mg: int
) -> JobSummary:
    """Compare what is still outstanding with what the agreement allows.

    Outstanding is fine gold issued minus fine gold returned. Unexplained is
    outstanding minus the allowed wastage, and is negative when the karigar
    lost less than the agreed allowance.
    """
    if isinstance(outstanding_mg, bool) or not isinstance(outstanding_mg, int):
        raise TypeError("Outstanding must be an integer")
    allowed = allowed_wastage_mg(issued_fine_mg, wastage_hundredths)
    return JobSummary(
        issued_mg=issued_fine_mg,
        returned_mg=issued_fine_mg - outstanding_mg,
        outstanding_mg=outstanding_mg,
        wastage_hundredths=wastage_hundredths,
        allowed_mg=allowed,
        unexplained_mg=outstanding_mg - allowed,
    )


def needs_review(status: str, unexplained_mg: int) -> bool:
    """Only a closed job can be reviewed, and only when loss exceeds the allowance."""
    return status == "CLOSED" and unexplained_mg > 0