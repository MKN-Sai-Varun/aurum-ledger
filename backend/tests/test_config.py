import pytest

from app.config import load_settings


def test_production_rejects_missing_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "")
    with pytest.raises(RuntimeError):
        load_settings()


def test_production_rejects_short_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "too-short")
    with pytest.raises(RuntimeError):
        load_settings()


def test_production_accepts_long_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    settings = load_settings()
    assert settings.is_production is True


def test_development_allows_missing_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "")
    settings = load_settings()
    assert settings.is_production is False
    assert settings.jwt_secret