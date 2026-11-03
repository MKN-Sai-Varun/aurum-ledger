import pytest

from app.domain.job_math import needs_review, summarise_job


def test_brief_sample_job():
    summary = summarise_job(109920, 300, 3893)
    assert summary.returned_mg == 106027
    assert summary.allowed_mg == 3298
    assert summary.unexplained_mg == 595


def test_loss_within_allowance_is_negative():
    summary = summarise_job(91600, 250, 2015)
    assert summary.allowed_mg == 2290
    assert summary.unexplained_mg == -275


def test_exactly_at_allowance_is_zero():
    summary = summarise_job(54960, 250, 1374)
    assert summary.allowed_mg == 1374
    assert summary.unexplained_mg == 0


def test_nothing_issued_gives_zeros():
    summary = summarise_job(0, 300, 0)
    assert (summary.returned_mg, summary.allowed_mg, summary.unexplained_mg) == (0, 0, 0)


def test_review_rules():
    assert needs_review("CLOSED", 1) is True
    assert needs_review("CLOSED", 0) is False
    assert needs_review("CLOSED", -5) is False
    assert needs_review("OPEN", 999) is False


def test_float_outstanding_rejected():
    with pytest.raises(TypeError):
        summarise_job(1000, 300, 10.5)


def test_negative_issue_rejected():
    with pytest.raises(ValueError):
        summarise_job(-1, 300, 0)