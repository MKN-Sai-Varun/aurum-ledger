import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Base, make_engine
from app.domain.gold_math import allowed_wastage_mg, fine_weight_mg
from app.models import (
    ItemCategory,
    Job,
    Karigar,
    KarigarWastage,
    LedgerEntry,
    User,
)
from app.security import verify_password
from app.seed import seed_database

CLERK_PW = "clerk-demo-pass-1"
FINANCE_PW = "finance-demo-pass-1"


@pytest.fixture()
def db():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, CLERK_PW, FINANCE_PW)
        yield session
    engine.dispose()


def unexplained_by_closed_job(db, karigar_name):
    karigar = db.scalar(select(Karigar).where(Karigar.name == karigar_name))
    jobs = db.scalars(
        select(Job)
        .where(Job.karigar_id == karigar.id, Job.status == "CLOSED")
        .order_by(Job.closed_on)
    ).all()
    result = []
    for job in jobs:
        entries = db.scalars(
            select(LedgerEntry).where(LedgerEntry.job_id == job.id)
        ).all()
        issue = next(e for e in entries if e.kind == "ISSUE")
        outstanding = sum(e.balance_delta_mg for e in entries)
        allowed = allowed_wastage_mg(issue.fine_mg, issue.wastage_hundredths)
        result.append(outstanding - allowed)
    return result


def test_two_users_with_expected_roles(db):
    roles = {u.username: u.role for u in db.scalars(select(User))}
    assert roles == {"clerk": "issue_clerk", "finance": "finance_head"}


def test_passwords_are_hashed_and_verifiable(db):
    clerk = db.scalar(select(User).where(User.username == "clerk"))
    assert clerk.password_hash != CLERK_PW
    assert verify_password(CLERK_PW, clerk.password_hash)
    assert not verify_password(FINANCE_PW, clerk.password_hash)


def test_expected_counts(db):
    assert db.scalar(select(func.count()).select_from(Karigar)) == 6
    assert db.scalar(select(func.count()).select_from(ItemCategory)) == 5
    assert db.scalar(select(func.count()).select_from(Job)) == 14
    assert db.scalar(select(func.count()).select_from(LedgerEntry)) == 39


def test_sample_rows_match_the_brief(db):
    expected = {
        "TX-30411": ("ISSUE", 120000, 109920),
        "TX-30437": ("RECEIPT_PIECE", 112450, 103004),
        "TX-30438": ("RECEIPT_SCRAP", 3300, 3023),
    }
    for txn_no, (kind, gross, fine) in expected.items():
        entry = db.scalar(select(LedgerEntry).where(LedgerEntry.txn_no == txn_no))
        karigar = db.get(Karigar, entry.karigar_id)
        assert karigar.name == "Murugesan S"
        assert entry.kind == kind
        assert entry.gross_mg == gross
        assert entry.fine_mg == fine
        assert entry.purity_hundredths == 9160
        assert entry.wastage_hundredths == 300


def test_sample_job_balance_is_3_893_grams(db):
    job = db.scalar(select(Job).where(Job.job_no == "JOB-1041"))
    balance = db.scalar(
        select(func.sum(LedgerEntry.balance_delta_mg)).where(
            LedgerEntry.job_id == job.id
        )
    )
    assert balance == 3893


def test_every_entry_maths_is_consistent(db):
    for entry in db.scalars(select(LedgerEntry)):
        assert entry.fine_mg == fine_weight_mg(entry.gross_mg, entry.purity_hundredths)
        if entry.kind == "ISSUE":
            assert entry.balance_delta_mg == entry.fine_mg
        else:
            assert entry.balance_delta_mg == -entry.fine_mg


def test_no_job_returns_more_gold_than_was_issued(db):
    for job in db.scalars(select(Job)):
        balance = db.scalar(
            select(func.sum(LedgerEntry.balance_delta_mg)).where(
                LedgerEntry.job_id == job.id
            )
        )
        assert balance >= 0, job.job_no


def test_closed_jobs_have_a_close_date_and_open_jobs_do_not(db):
    for job in db.scalars(select(Job)):
        if job.status == "CLOSED":
            assert job.closed_on is not None
        else:
            assert job.closed_on is None


def test_wastage_snapshot_matches_the_master_rate(db):
    for entry in db.scalars(select(LedgerEntry)):
        job = db.get(Job, entry.job_id)
        rate = db.scalar(
            select(KarigarWastage.wastage_hundredths).where(
                KarigarWastage.karigar_id == entry.karigar_id,
                KarigarWastage.category_id == job.category_id,
            )
        )
        assert entry.wastage_hundredths == rate


def test_huid_only_on_finished_pieces(db):
    for entry in db.scalars(select(LedgerEntry)):
        if entry.kind == "RECEIPT_PIECE":
            assert entry.huid
        else:
            assert entry.huid is None


def test_selvam_loss_beyond_allowance_rises_job_by_job(db):
    # Values in milligrams: outstanding gold minus allowed wastage.
    assert unexplained_by_closed_job(db, "Selvam K") == [-275, -92, 549, 1374]


def test_seed_refuses_a_second_run(db):
    with pytest.raises(RuntimeError):
        seed_database(db, CLERK_PW, FINANCE_PW)