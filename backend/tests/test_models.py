from datetime import date

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.db import Base, make_engine
from app.domain.gold_math import (
    fine_weight_mg,
    parse_purity_pct,
    parse_weight_g,
)
from app.models import (
    AuditLog,
    ItemCategory,
    Job,
    Karigar,
    KarigarWastage,
    LedgerEntry,
    User,
)


@pytest.fixture()
def session():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


@pytest.fixture()
def world(session):
    user = User(
        username="clerk1",
        full_name="Test Clerk",
        password_hash="not-a-real-hash",
        role="issue_clerk",
    )
    karigar = Karigar(name="Murugesan S")
    category = ItemCategory(name="Necklace")
    session.add_all([user, karigar, category])
    session.flush()
    job = Job(
        job_no="JOB-001",
        karigar_id=karigar.id,
        category_id=category.id,
        opened_on=date(2026, 10, 1),
        created_by=user.id,
    )
    session.add(job)
    session.commit()
    return {"user": user, "karigar": karigar, "category": category, "job": job}


def make_entry(w, **overrides):
    values = dict(
        txn_no="TX-30411",
        entry_date=date(2026, 10, 1),
        karigar_id=w["karigar"].id,
        job_id=w["job"].id,
        kind="ISSUE",
        gross_mg=120000,
        purity_hundredths=9160,
        fine_mg=109920,
        wastage_hundredths=300,
        balance_delta_mg=109920,
        created_by=w["user"].id,
    )
    values.update(overrides)
    return LedgerEntry(**values)


def test_sample_ledger_balance_from_database(session, world):
    purity = parse_purity_pct("91.60")
    issue = fine_weight_mg(parse_weight_g("120.000"), purity)
    piece = fine_weight_mg(parse_weight_g("112.450"), purity)
    scrap = fine_weight_mg(parse_weight_g("3.300"), purity)
    session.add_all(
        [
            make_entry(world, txn_no="TX-30411", kind="ISSUE",
                       gross_mg=120000, fine_mg=issue, balance_delta_mg=issue),
            make_entry(world, txn_no="TX-30437", kind="RECEIPT_PIECE",
                       gross_mg=112450, fine_mg=piece, balance_delta_mg=-piece,
                       huid="AB1234"),
            make_entry(world, txn_no="TX-30438", kind="RECEIPT_SCRAP",
                       gross_mg=3300, fine_mg=scrap, balance_delta_mg=-scrap),
        ]
    )
    session.commit()
    balance = session.execute(
        select(func.sum(LedgerEntry.balance_delta_mg))
    ).scalar_one()
    assert balance == 3893  # 3.893 g, as in the brief


def test_ledger_entry_cannot_be_updated(session, world):
    session.add(make_entry(world))
    session.commit()
    with pytest.raises(DBAPIError):
        session.execute(text("UPDATE ledger_entries SET gross_mg = 1"))


def test_ledger_entry_cannot_be_deleted(session, world):
    session.add(make_entry(world))
    session.commit()
    with pytest.raises(DBAPIError):
        session.execute(text("DELETE FROM ledger_entries"))


def test_audit_log_cannot_be_updated(session, world):
    session.add(AuditLog(user_id=world["user"].id, action="login", entity="user"))
    session.commit()
    with pytest.raises(DBAPIError):
        session.execute(text("UPDATE audit_log SET action = 'x'"))


def test_audit_log_cannot_be_deleted(session, world):
    session.add(AuditLog(user_id=world["user"].id, action="login", entity="user"))
    session.commit()
    with pytest.raises(DBAPIError):
        session.execute(text("DELETE FROM audit_log"))


def test_duplicate_txn_no_rejected(session, world):
    session.add(make_entry(world))
    session.commit()
    session.add(make_entry(world))
    with pytest.raises(IntegrityError):
        session.commit()


def test_invalid_role_rejected(session):
    session.add(
        User(username="x", full_name="X", password_hash="h", role="admin")
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_negative_weight_rejected(session, world):
    session.add(make_entry(world, gross_mg=-1))
    with pytest.raises(IntegrityError):
        session.commit()


def test_zero_purity_rejected(session, world):
    session.add(make_entry(world, purity_hundredths=0))
    with pytest.raises(IntegrityError):
        session.commit()


def test_reversal_without_reference_rejected(session, world):
    session.add(make_entry(world, kind="REVERSAL"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_non_reversal_with_reference_rejected(session, world):
    original = make_entry(world)
    session.add(original)
    session.commit()
    session.add(
        make_entry(world, txn_no="TX-30412", reverses_entry_id=original.id)
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_valid_reversal_cancels_the_original(session, world):
    original = make_entry(world)
    session.add(original)
    session.commit()
    session.add(
        make_entry(
            world,
            txn_no="TX-30412",
            kind="REVERSAL",
            reverses_entry_id=original.id,
            balance_delta_mg=-109920,
        )
    )
    session.commit()
    balance = session.execute(
        select(func.sum(LedgerEntry.balance_delta_mg))
    ).scalar_one()
    assert balance == 0


def test_entry_can_only_be_reversed_once(session, world):
    original = make_entry(world)
    session.add(original)
    session.commit()
    session.add(
        make_entry(world, txn_no="TX-30412", kind="REVERSAL",
                   reverses_entry_id=original.id, balance_delta_mg=-109920)
    )
    session.commit()
    session.add(
        make_entry(world, txn_no="TX-30413", kind="REVERSAL",
                   reverses_entry_id=original.id, balance_delta_mg=-109920)
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_foreign_keys_are_enforced(session, world):
    session.add(make_entry(world, karigar_id=9999))
    with pytest.raises(IntegrityError):
        session.commit()


def test_one_wastage_rate_per_karigar_and_category(session, world):
    k, c = world["karigar"].id, world["category"].id
    session.add(KarigarWastage(karigar_id=k, category_id=c, wastage_hundredths=300))
    session.commit()
    session.add(KarigarWastage(karigar_id=k, category_id=c, wastage_hundredths=250))
    with pytest.raises(IntegrityError):
        session.commit()