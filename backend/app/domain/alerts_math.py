"""Loss-trend checks. Pure functions with no database access.

The difference on a closed job is the fine gold still outstanding minus the
agreed wastage. It is compared as hundredths of a percent of the fine gold
issued, so jobs of different sizes can be compared.
"""
from dataclasses import dataclass
from datetime import date

DRIFT_MIN_JOBS = 3
DRIFT_THRESHOLD_H = 50  # 0.50 percentage points


@dataclass(frozen=True)
class JobLoss:
    job_no: str
    closed_on: date
    issued_mg: int
    unexplained_mg: int


@dataclass(frozen=True)
class Drift:
    latest_job_no: str
    latest_rate_h: int
    baseline_rate_h: int
    earlier_jobs: int
    difference_h: int


def loss_rate_h(unexplained_mg: int, issued_mg: int) -> int:
    """Unexplained difference as hundredths of a percent of the fine issued, half-up."""
    for value, label in ((unexplained_mg, "Unexplained"), (issued_mg, "Issued")):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{label} must be an integer")
    if issued_mg <= 0:
        raise ValueError("Issued must be above 0")
    return (2 * unexplained_mg * 10_000 + issued_mg) // (2 * issued_mg)


def _mean_h(values: list[int]) -> int:
    count = len(values)
    return (2 * sum(values) + count) // (2 * count)


def detect_drift(jobs: list[JobLoss]) -> Drift | None:
    """Compare a karigar's latest closed job with their own earlier jobs."""
    usable = sorted(
        (job for job in jobs if job.issued_mg > 0),
        key=lambda job: (job.closed_on, job.job_no),
    )
    if len(usable) < DRIFT_MIN_JOBS:
        return None
    *history, latest = usable
    baseline = _mean_h([loss_rate_h(j.unexplained_mg, j.issued_mg) for j in history])
    latest_rate = loss_rate_h(latest.unexplained_mg, latest.issued_mg)
    difference = latest_rate - baseline
    if latest_rate > 0 and difference >= DRIFT_THRESHOLD_H:
        return Drift(
            latest_job_no=latest.job_no,
            latest_rate_h=latest_rate,
            baseline_rate_h=baseline,
            earlier_jobs=len(history),
            difference_h=difference,
        )
    return None