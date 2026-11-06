"""Seed the database with fake demo data.

All names, numbers and HUIDs are invented. The three Murugesan S rows
come from the client brief. Run with:  python -m app.seed
Demo passwords are read from the DEMO_CLERK_PASSWORD and
DEMO_FINANCE_PASSWORD environment variables and are never stored in code.
"""
import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import load_settings
from app.db import Base, SessionLocal, engine
from app.domain.old_gold_math import parse_rupees, value_paise
from app.domain.gold_math import (
    fine_weight_mg,
    parse_purity_pct,
    parse_wastage_pct,
    parse_weight_g,
)
from app.models import (
    KIND_ISSUE,
    KIND_RECEIPT_FILINGS,
    KIND_RECEIPT_PIECE,
    KIND_RECEIPT_SCRAP,
    ROLE_FINANCE_HEAD,
    ROLE_ISSUE_CLERK,
    AuditLog,
    ItemCategory,
    Job,
    Karigar,
    KarigarWastage,
    LedgerEntry,
    User,
    STOCK_FROM_REFINER,
    STOCK_OPENING,
    STOCK_TO_REFINER,
    StockEntry,
    PAY_BANK,
    PAY_CASH,
    OldGoldPurchase,
    ROLE_KARIGAR,
    JobFollowUp,
)
from app.security import hash_password

CATEGORIES = ["Necklace", "Chain", "Bangle", "Ring", "Earring"]

# Agreed wastage percentage per karigar and item category (fake values).
KARIGAR_WASTAGE = {
    "Murugesan S": {"Necklace": "3.00", "Chain": "2.50", "Bangle": "2.00"},
    "Selvam K": {"Chain": "2.50", "Ring": "3.50", "Earring": "4.00"},
    "Ramesh P": {"Bangle": "2.00", "Necklace": "3.00"},
    "Anbu R": {"Ring": "3.50", "Earring": "4.00"},
    "Karthik M": {"Chain": "2.50", "Bangle": "2.00"},
    "Dhanapal V": {"Necklace": "3.00", "Earring": "4.00"},
}

OLD_GOLD = [
    ("OG-5001", "EXB-2026-0412", date(2026, 10, 28), "Lakshmi R",
     "25.000", "0.500", "84.50", "12500.00", PAY_BANK, "FGHIJ5678K"),
    ("OG-5002", "EXB-2026-0419", date(2026, 10, 31), "Karim S",
     "8.200", "0", "76.00", "12500.00", PAY_CASH, None),
    ("OG-5003", "EXB-2026-0425", date(2026, 11, 2), "Priya M",
     "52.000", "1.250", "91.60", "12500.00", PAY_CASH, "ABCDE1234F"),
]

@dataclass(frozen=True)
class ReceiptSpec:
    on: date
    kind: str
    gross: str
    purity: str = "91.60"


@dataclass(frozen=True)
class JobSpec:
    job_no: str
    karigar: str
    category: str
    opened: date
    closed: date | None
    issue_gross: str
    receipts: tuple = ()
    issue_purity: str = "91.60"
    fixed_txns: tuple = ()  # transaction numbers fixed by the brief


def _r(on, kind, gross):
    return ReceiptSpec(on=on, kind=kind, gross=gross)


PIECE, SCRAP, FILINGS = KIND_RECEIPT_PIECE, KIND_RECEIPT_SCRAP, KIND_RECEIPT_FILINGS

JOBS = [
    # Murugesan S. JOB-1041 reproduces the three sample rows from the brief.
    JobSpec("JOB-1019", "Murugesan S", "Chain", date(2026, 9, 2), date(2026, 9, 12),
            "60.000", (_r(date(2026, 9, 12), PIECE, "57.500"),
                       _r(date(2026, 9, 12), SCRAP, "1.000"))),
    JobSpec("JOB-1041", "Murugesan S", "Necklace", date(2026, 10, 20), date(2026, 10, 27),
            "120.000", (_r(date(2026, 10, 27), PIECE, "112.450"),
                        _r(date(2026, 10, 27), SCRAP, "3.300")),
            fixed_txns=("TX-30411", "TX-30437", "TX-30438")),
    # Selvam K: loss beyond allowed wastage rises job by job (for drift alerts).
    JobSpec("JOB-1003", "Selvam K", "Chain", date(2026, 7, 6), date(2026, 7, 18),
            "100.000", (_r(date(2026, 7, 18), PIECE, "95.800"),
                        _r(date(2026, 7, 18), SCRAP, "2.000"))),
    JobSpec("JOB-1012", "Selvam K", "Chain", date(2026, 8, 10), date(2026, 8, 22),
            "100.000", (_r(date(2026, 8, 22), PIECE, "95.600"),
                        _r(date(2026, 8, 22), SCRAP, "2.000"))),
    JobSpec("JOB-1027", "Selvam K", "Chain", date(2026, 9, 8), date(2026, 9, 20),
            "100.000", (_r(date(2026, 9, 20), PIECE, "94.800"),
                        _r(date(2026, 9, 20), SCRAP, "2.100"))),
    JobSpec("JOB-1038", "Selvam K", "Chain", date(2026, 10, 12), date(2026, 10, 24),
            "100.000", (_r(date(2026, 10, 24), PIECE, "94.000"),
                        _r(date(2026, 10, 24), SCRAP, "2.000"))),
    # Other karigars: steady, small differences, plus a few open jobs.
    JobSpec("JOB-1024", "Ramesh P", "Bangle", date(2026, 9, 15), date(2026, 9, 26),
            "90.000", (_r(date(2026, 9, 26), PIECE, "85.300"),
                       _r(date(2026, 9, 26), SCRAP, "1.800"),
                       _r(date(2026, 9, 26), FILINGS, "0.900"))),
    JobSpec("JOB-1044", "Ramesh P", "Necklace", date(2026, 10, 30), None, "75.000"),
    JobSpec("JOB-1031", "Anbu R", "Ring", date(2026, 9, 29), date(2026, 10, 8),
            "40.000", (_r(date(2026, 10, 8), PIECE, "37.900"),
                       _r(date(2026, 10, 8), SCRAP, "0.800"),
                       _r(date(2026, 10, 8), FILINGS, "0.500"))),
    JobSpec("JOB-1045", "Anbu R", "Earring", date(2026, 10, 31), None, "30.000"),
    JobSpec("JOB-1029", "Karthik M", "Bangle", date(2026, 9, 24), date(2026, 10, 5),
            "110.000", (_r(date(2026, 10, 5), PIECE, "104.000"),
                        _r(date(2026, 10, 5), SCRAP, "2.500"),
                        _r(date(2026, 10, 5), FILINGS, "1.000"))),
    JobSpec("JOB-1043", "Karthik M", "Chain", date(2026, 10, 29), None, "85.000"),
    JobSpec("JOB-1035", "Dhanapal V", "Necklace", date(2026, 10, 3), date(2026, 10, 14),
            "95.000", (_r(date(2026, 10, 14), PIECE, "89.700"),
                       _r(date(2026, 10, 14), SCRAP, "2.200"),
                       _r(date(2026, 10, 14), FILINGS, "0.600"))),
    JobSpec("JOB-1046", "Dhanapal V", "Earring", date(2026, 10, 30), None, "25.000",
            (_r(date(2026, 11, 1), PIECE, "10.000"),)),
]

_EPOCH = date(2026, 7, 1)


@dataclass
class _Row:
    on: date
    order: int
    spec: JobSpec
    kind: str
    gross: str
    purity: str
    fixed_txn: str | None
    txn: str = ""


def _build_rows() -> list:
    rows, order = [], 0
    for spec in JOBS:
        fixed = list(spec.fixed_txns)
        rows.append(_Row(spec.opened, order, spec, KIND_ISSUE, spec.issue_gross,
                         spec.issue_purity, fixed.pop(0) if fixed else None))
        order += 1
        for receipt in spec.receipts:
            rows.append(_Row(receipt.on, order, spec, receipt.kind, receipt.gross,
                             receipt.purity, fixed.pop(0) if fixed else None))
            order += 1
    rows.sort(key=lambda row: (row.on, row.order))

    used = {row.fixed_txn for row in rows if row.fixed_txn}
    per_day: dict = {}
    for row in rows:
        if row.fixed_txn:
            row.txn = row.fixed_txn
            continue
        per_day[row.on] = per_day.get(row.on, 0) + 1
        number = 30000 + ((row.on - _EPOCH).days * 37) // 10 + per_day[row.on]
        while f"TX-{number}" in used:
            number += 1
        row.txn = f"TX-{number}"
        used.add(row.txn)
    return rows


def seed_database(
    session: Session,
    clerk_password: str,
    finance_password: str,
    karigar_password: str | None = None,
) -> None:
    if session.scalar(select(User.id).limit(1)) is not None:
        raise RuntimeError("Database already contains data. Use --reset in development.")

    clerk = User(username="clerk", full_name="Demo Issue Clerk",
                 password_hash=hash_password(clerk_password), role=ROLE_ISSUE_CLERK)
    finance = User(username="finance", full_name="Demo Finance Head",
                   password_hash=hash_password(finance_password), role=ROLE_FINANCE_HEAD)
    categories = {name: ItemCategory(name=name) for name in CATEGORIES}
    karigars = {name: Karigar(name=name) for name in KARIGAR_WASTAGE}
    session.add_all([clerk, finance, *categories.values(), *karigars.values()])
    session.flush()

    if karigar_password:
        session.add(User(
            username="murugesan", full_name="Murugesan S",
            password_hash=hash_password(karigar_password),
            role=ROLE_KARIGAR, karigar_id=karigars["Murugesan S"].id,
        ))
        session.flush()

    wastage = {}
    for karigar_name, rates in KARIGAR_WASTAGE.items():
        for category_name, text in rates.items():
            value = parse_wastage_pct(text)
            wastage[(karigar_name, category_name)] = value
            session.add(KarigarWastage(
                karigar_id=karigars[karigar_name].id,
                category_id=categories[category_name].id,
                wastage_hundredths=value,
            ))

    jobs = {}
    for spec in JOBS:
        job = Job(job_no=spec.job_no, karigar_id=karigars[spec.karigar].id,
                  category_id=categories[spec.category].id,
                  status="CLOSED" if spec.closed else "OPEN",
                  opened_on=spec.opened, closed_on=spec.closed, created_by=clerk.id)
        jobs[spec.job_no] = job
        session.add(job)
    session.flush()

    rows = _build_rows()
    huid_counter = 0
    for row in rows:
        spec = row.spec
        gross_mg = parse_weight_g(row.gross)
        purity = parse_purity_pct(row.purity)
        fine = fine_weight_mg(gross_mg, purity)
        huid = None
        if row.kind == KIND_RECEIPT_PIECE:
            huid_counter += 1
            huid = f"H{huid_counter:05d}"  # clearly fake
        session.add(LedgerEntry(
            txn_no=row.txn, entry_date=row.on,
            karigar_id=karigars[spec.karigar].id, job_id=jobs[spec.job_no].id,
            kind=row.kind, gross_mg=gross_mg, purity_hundredths=purity, fine_mg=fine,
            wastage_hundredths=wastage[(spec.karigar, spec.category)],
            balance_delta_mg=fine if row.kind == KIND_ISSUE else -fine,
            huid=huid, created_by=clerk.id,
        ))
    session.add_all(
        [
            StockEntry(entry_date=date(2026, 7, 1), kind=STOCK_OPENING, fine_mg=2_500_000,
                       note="Opening vault stock (sample figure)", created_by=finance.id),
            StockEntry(entry_date=date(2026, 10, 15), kind=STOCK_TO_REFINER, fine_mg=150_000,
                       note="Sent for refining (sample figure)", created_by=finance.id),
            StockEntry(entry_date=date(2026, 10, 25), kind=STOCK_FROM_REFINER, fine_mg=40_000,
                       note="Part returned from refining (sample figure)", created_by=finance.id),
        ]
    )
    session.add(JobFollowUp(
        job_id=jobs["JOB-1043"].id,
        note="Asked for an update, expected back next week",
        followed_up_on=date(2026, 11, 4),
        created_by=finance.id,
    ))
    for (og_no, bill, day, customer, gross_text, deduction_text,purity_text, rate_text, mode, pan) in OLD_GOLD:
        gross_mg = parse_weight_g(gross_text)
        deduction_mg = parse_weight_g(deduction_text)
        purity = parse_purity_pct(purity_text)
        fine = fine_weight_mg(gross_mg - deduction_mg, purity)
        rate = parse_rupees(rate_text)
        session.add(OldGoldPurchase(
            og_no=og_no, entry_date=day, bill_no=bill, customer_name=customer,
            gross_mg=gross_mg, deduction_mg=deduction_mg, purity_hundredths=purity,
            fine_mg=fine, rate_paise=rate, value_paise=value_paise(fine, rate),
            payment_mode=mode, pan=pan, note=None, created_by=clerk.id,
        )
    )
    session.add(AuditLog(user_id=None, action="seed.completed", entity="database",
                         detail=f"{len(rows)} ledger entries"))
    session.commit()


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Seed demo data.")
    parser.add_argument("--reset", action="store_true",
                        help="Drop and recreate all tables first (development only).")
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.reset and settings.is_production:
        sys.exit("Refusing to use --reset in production.")

    clerk_password = os.getenv("DEMO_CLERK_PASSWORD", "").strip()
    finance_password = os.getenv("DEMO_FINANCE_PASSWORD", "").strip()
    karigar_password = os.getenv("DEMO_KARIGAR_PASSWORD", "").strip() or None
    if not clerk_password or not finance_password:
        sys.exit("Set DEMO_CLERK_PASSWORD and DEMO_FINANCE_PASSWORD (see .env.example).")

    if args.reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with SessionLocal() as session:
        try:
            seed_database(session, clerk_password, finance_password, karigar_password)
        except (RuntimeError, ValueError) as error:
            sys.exit(str(error))
        print("Seeded demo data. Users: clerk, finance" + (", murugesan." if karigar_password else "."))


if __name__ == "__main__":
    main()