import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import sessionmaker

from app.bootstrap import bootstrap
from app.db import make_engine
from app.models import User


def fresh():
    engine = make_engine("sqlite://")
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def enable(monkeypatch, karigar=None):
    monkeypatch.setenv("AUTO_SEED", "true")
    monkeypatch.setenv("DEMO_CLERK_PASSWORD", "clerk-demo-pass-1")
    monkeypatch.setenv("DEMO_FINANCE_PASSWORD", "finance-demo-pass-1")
    if karigar:
        monkeypatch.setenv("DEMO_KARIGAR_PASSWORD", karigar)
    else:
        monkeypatch.delenv("DEMO_KARIGAR_PASSWORD", raising=False)


def users(maker):
    with maker() as session:
        return session.scalar(select(func.count()).select_from(User))


def test_does_nothing_unless_enabled(monkeypatch):
    monkeypatch.delenv("AUTO_SEED", raising=False)
    engine, maker = fresh()
    bootstrap(engine, maker)
    assert inspect(engine).get_table_names() == []


def test_seeds_an_empty_database(monkeypatch):
    enable(monkeypatch)
    engine, maker = fresh()
    bootstrap(engine, maker)
    assert users(maker) == 2


def test_does_not_seed_twice(monkeypatch):
    enable(monkeypatch)
    engine, maker = fresh()
    bootstrap(engine, maker)
    bootstrap(engine, maker)
    assert users(maker) == 2


def test_refuses_to_start_without_demo_passwords(monkeypatch):
    monkeypatch.setenv("AUTO_SEED", "true")
    monkeypatch.delenv("DEMO_CLERK_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_FINANCE_PASSWORD", raising=False)
    engine, maker = fresh()
    with pytest.raises(RuntimeError):
        bootstrap(engine, maker)

def test_seeds_the_karigar_login_when_a_password_is_given(monkeypatch):
    enable(monkeypatch, karigar="karigar-demo-pass-1")
    engine, maker = fresh()
    bootstrap(engine, maker)
    assert users(maker) == 3