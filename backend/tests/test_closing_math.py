import pytest

from app.domain.closing_math import difference_mg, reconciles


def test_difference_is_counted_minus_expected():
    assert difference_mg(2_252_509, 2_252_514) == -5
    assert difference_mg(100, 100) == 0
    assert difference_mg(150, 100) == 50


def test_reconciles_when_the_movements_add_up():
    assert reconciles(2_206_027, [46_487, 0, 0], 2_252_514) is True
    assert reconciles(1000, [], 1000) is True
    assert reconciles(1000, [-300, 200], 900) is True


def test_does_not_reconcile_when_a_gram_is_missing():
    assert reconciles(1000, [-300, 200], 901) is False


def test_rejects_floats_and_booleans():
    with pytest.raises(TypeError):
        difference_mg(1.5, 1)
    with pytest.raises(TypeError):
        reconciles(True, [], 1)
    with pytest.raises(TypeError):
        reconciles(1, [2.5], 1)