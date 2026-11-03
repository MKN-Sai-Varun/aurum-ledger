from datetime import date

import pytest

from app.domain.alerts_math import JobLoss, detect_drift, loss_rate_h


def job(no, day, issued, unexplained):
    return JobLoss(no, date(2026, 9, day), issued, unexplained)


def test_rates_round_half_up_including_negatives():
    assert loss_rate_h(-275, 91600) == -30
    assert loss_rate_h(-92, 91600) == -10
    assert loss_rate_h(549, 91600) == 60
    assert loss_rate_h(1374, 91600) == 150
    assert loss_rate_h(0, 91600) == 0


def test_rate_rejects_bad_input():
    with pytest.raises(ValueError):
        loss_rate_h(10, 0)
    with pytest.raises(TypeError):
        loss_rate_h(10.5, 1000)


def test_seeded_pattern_is_flagged():
    jobs = [
        job("JOB-1003", 1, 91600, -275),
        job("JOB-1012", 2, 91600, -92),
        job("JOB-1027", 3, 91600, 549),
        job("JOB-1038", 4, 91600, 1374),
    ]
    drift = detect_drift(jobs)
    assert drift is not None
    assert drift.latest_job_no == "JOB-1038"
    assert drift.latest_rate_h == 150
    assert drift.baseline_rate_h == 7
    assert drift.earlier_jobs == 3
    assert drift.difference_h == 143


def test_too_few_jobs_gives_nothing():
    assert detect_drift([job("A", 1, 10000, 0), job("B", 2, 10000, 900)]) is None


def test_latest_within_allowance_is_not_flagged():
    jobs = [job("A", 1, 10000, -900), job("B", 2, 10000, -800), job("C", 3, 10000, -100)]
    assert detect_drift(jobs) is None


def test_exactly_the_threshold_is_flagged_and_one_below_is_not():
    base = [job("A", 1, 10000, 0), job("B", 2, 10000, 0)]
    assert detect_drift(base + [job("C", 3, 10000, 50)]) is not None
    assert detect_drift(base + [job("C", 3, 10000, 49)]) is None


def test_input_order_does_not_matter():
    jobs = [
        job("C", 3, 10000, 80),
        job("A", 1, 10000, 0),
        job("B", 2, 10000, 0),
    ]
    assert detect_drift(jobs).latest_job_no == "C"


def test_jobs_with_nothing_issued_are_ignored():
    jobs = [job("A", 1, 10000, 0), job("B", 2, 10000, 0), job("Z", 3, 0, 0)]
    assert detect_drift(jobs) is None