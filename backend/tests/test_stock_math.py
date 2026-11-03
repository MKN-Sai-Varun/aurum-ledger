import pytest

from app.domain.stock_math import compute_statement


def test_seed_figures_add_up():
    s = compute_statement(2_500_000, 150_000, 40_000, 210_908)
    assert (s.vault_mg, s.karigars_mg, s.refiner_mg, s.total_mg) == (2_179_092, 210_908, 110_000, 2_500_000)
    assert s.consistent is True


def test_nothing_anywhere_is_all_zero():
    s = compute_statement(0, 0, 0, 0)
    assert (s.vault_mg, s.refiner_mg) == (0, 0)
    assert s.consistent is True


def test_more_out_than_in_is_flagged():
    assert compute_statement(100, 0, 0, 150).consistent is False
    assert compute_statement(100, 0, 10, 0).consistent is False


def test_every_gram_is_accounted_for():
    s = compute_statement(5_000, 700, 200, 1_234)
    assert s.vault_mg + s.karigars_mg + s.refiner_mg == s.total_mg


def test_rejects_floats_and_booleans():
    with pytest.raises(TypeError):
        compute_statement(1.5, 0, 0, 0)
    with pytest.raises(TypeError):
        compute_statement(True, 0, 0, 0)