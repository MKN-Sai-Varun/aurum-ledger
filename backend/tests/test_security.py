import pytest

from app.security import hash_password, verify_password


def test_hash_is_not_the_plain_password():
    hashed = hash_password("a-long-demo-password")
    assert hashed != "a-long-demo-password"
    assert "a-long-demo-password" not in hashed


def test_verify_accepts_correct_and_rejects_wrong_password():
    hashed = hash_password("a-long-demo-password")
    assert verify_password("a-long-demo-password", hashed) is True
    assert verify_password("another-password-1", hashed) is False


def test_same_password_gives_different_hashes():
    assert hash_password("a-long-demo-password") != hash_password("a-long-demo-password")


def test_short_password_rejected():
    with pytest.raises(ValueError):
        hash_password("short")


def test_verify_returns_false_for_garbage_hash():
    assert verify_password("a-long-demo-password", "not-a-hash") is False