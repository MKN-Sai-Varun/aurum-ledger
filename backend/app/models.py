"""Database models for Aurum.

Weights are integer milligrams and percentages are integer hundredths of a
percent (see app/domain/gold_math.py). The ledger and audit tables are
append-only, enforced by database triggers as well as application code.
"""
from datetime import date, datetime, timezone

from sqlalchemy import (
    DDL,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ROLE_ISSUE_CLERK = "issue_clerk"
ROLE_FINANCE_HEAD = "finance_head"

KIND_ISSUE = "ISSUE"
KIND_RECEIPT_PIECE = "RECEIPT_PIECE"
KIND_RECEIPT_SCRAP = "RECEIPT_SCRAP"
KIND_RECEIPT_FILINGS = "RECEIPT_FILINGS"
KIND_REVERSAL = "REVERSAL"
STOCK_OPENING = "OPENING"
STOCK_TO_REFINER = "TO_REFINER"
STOCK_FROM_REFINER = "FROM_REFINER"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('issue_clerk', 'finance_head')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ItemCategory(Base):
    __tablename__ = "item_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)


class Karigar(Base):
    __tablename__ = "karigars"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class KarigarWastage(Base):
    """Agreed wastage percentage for one karigar and one item category."""

    __tablename__ = "karigar_wastage"
    __table_args__ = (
        UniqueConstraint("karigar_id", "category_id", name="uq_wastage_karigar_category"),
        CheckConstraint(
            "wastage_hundredths BETWEEN 0 AND 10000", name="ck_wastage_range"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    karigar_id: Mapped[int] = mapped_column(ForeignKey("karigars.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("item_categories.id"))
    wastage_hundredths: Mapped[int] = mapped_column(Integer)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_jobs_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_no: Mapped[str] = mapped_column(String(20), unique=True)
    karigar_id: Mapped[int] = mapped_column(ForeignKey("karigars.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("item_categories.id"))
    status: Mapped[str] = mapped_column(String(10), default="OPEN")
    opened_on: Mapped[date] = mapped_column(Date)
    closed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class LedgerEntry(Base):
    """One movement of gold. Never updated or deleted, only reversed."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('ISSUE', 'RECEIPT_PIECE', 'RECEIPT_SCRAP', "
            "'RECEIPT_FILINGS', 'REVERSAL')",
            name="ck_ledger_kind",
        ),
        CheckConstraint("gross_mg >= 0", name="ck_ledger_gross"),
        CheckConstraint("fine_mg >= 0", name="ck_ledger_fine"),
        CheckConstraint(
            "purity_hundredths BETWEEN 1 AND 10000", name="ck_ledger_purity"
        ),
        CheckConstraint(
            "wastage_hundredths BETWEEN 0 AND 10000", name="ck_ledger_wastage"
        ),
        CheckConstraint(
            "(kind = 'REVERSAL') = (reverses_entry_id IS NOT NULL)",
            name="ck_ledger_reversal_link",
        ),
        Index("ix_ledger_karigar_date", "karigar_id", "entry_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    txn_no: Mapped[str] = mapped_column(String(20), unique=True)
    entry_date: Mapped[date] = mapped_column(Date)
    karigar_id: Mapped[int] = mapped_column(ForeignKey("karigars.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    kind: Mapped[str] = mapped_column(String(20))
    gross_mg: Mapped[int] = mapped_column(Integer)
    purity_hundredths: Mapped[int] = mapped_column(Integer)
    fine_mg: Mapped[int] = mapped_column(Integer)
    # Snapshot of the agreed wastage at the time, so later changes to the
    # karigar master never rewrite history.
    wastage_hundredths: Mapped[int] = mapped_column(Integer)
    # Signed effect on the karigar's fine-gold balance.
    balance_delta_mg: Mapped[int] = mapped_column(Integer)
    huid: Mapped[str | None] = mapped_column(String(12), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reverses_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("ledger_entries.id"), nullable=True, unique=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)

class StockEntry(Base):
    """Vault stock and refiner movements, in milligrams of fine gold. Append-only."""

    __tablename__ = "stock_entries"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('OPENING', 'TO_REFINER', 'FROM_REFINER')", name="ck_stock_kind"
        ),
        CheckConstraint("fine_mg > 0", name="ck_stock_fine"),
        Index("ix_stock_entry_date", "entry_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20))
    fine_mg: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
READING_PENDING = "PENDING"
READING_ACCEPTED = "ACCEPTED"
READING_CORRECTED = "CORRECTED"


class Reading(Base):
    """One attempt to read a value from a photo. The photo itself is never stored."""

    __tablename__ = "readings"
    __table_args__ = (
        CheckConstraint("target IN ('WEIGHT', 'PURITY')", name="ck_reading_target"),
        CheckConstraint(
            "source IN ('GEMINI', 'TESSERACT', 'NONE')", name="ck_reading_source"
        ),
        CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'CORRECTED')", name="ck_reading_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    target: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(10))
    value_text: Mapped[str | None] = mapped_column(String(12), nullable=True)
    image_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(10), default=READING_PENDING)
    confirmed_text: Mapped[str | None] = mapped_column(String(12), nullable=True)
    override_reason: Mapped[str | None] = mapped_column(String(150), nullable=True)
    txn_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
PAY_CASH = "CASH"
PAY_BANK = "BANK_TRANSFER"
PAY_UPI = "UPI"
PAY_CHEQUE = "CHEQUE"
PAY_ADJUSTED = "ADJUSTED"


class OldGoldPurchase(Base):
    """Old gold bought from a customer. Weights are mg and money is paise. Append-only."""

    __tablename__ = "old_gold_purchases"
    __table_args__ = (
        CheckConstraint("gross_mg > 0", name="ck_og_gross"),
        CheckConstraint("deduction_mg >= 0 AND deduction_mg < gross_mg", name="ck_og_deduction"),
        CheckConstraint("purity_hundredths BETWEEN 1 AND 10000", name="ck_og_purity"),
        CheckConstraint("fine_mg > 0", name="ck_og_fine"),
        CheckConstraint("rate_paise > 0", name="ck_og_rate"),
        CheckConstraint("value_paise >= 0", name="ck_og_value"),
        CheckConstraint(
            "payment_mode IN ('CASH', 'BANK_TRANSFER', 'UPI', 'CHEQUE', 'ADJUSTED')",
            name="ck_og_payment",
        ),
        CheckConstraint("pan IS NULL OR length(pan) = 10", name="ck_og_pan"),
        Index("ix_og_date", "entry_date"),
        Index("ix_og_bill", "bill_no"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    og_no: Mapped[str] = mapped_column(String(20), unique=True)
    entry_date: Mapped[date] = mapped_column(Date)
    bill_no: Mapped[str] = mapped_column(String(30))
    customer_name: Mapped[str] = mapped_column(String(100))
    gross_mg: Mapped[int] = mapped_column(Integer)
    deduction_mg: Mapped[int] = mapped_column(Integer)
    purity_hundredths: Mapped[int] = mapped_column(Integer)
    fine_mg: Mapped[int] = mapped_column(Integer)
    rate_paise: Mapped[int] = mapped_column(Integer)
    value_paise: Mapped[int] = mapped_column(Integer)
    payment_mode: Mapped[str] = mapped_column(String(20))
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class OldGoldVoid(Base):
    """A purchase cancelled by the finance head. Append-only, dated, with a reason."""

    __tablename__ = "old_gold_voids"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("old_gold_purchases.id"), unique=True
    )
    reason: Mapped[str] = mapped_column(String(150))
    voided_on: Mapped[date] = mapped_column(Date)
    voided_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

def _make_append_only(table) -> None:
    """Reject UPDATE and DELETE on a table (SQLite triggers)."""
    for operation in ("UPDATE", "DELETE"):
        ddl = DDL(
            f"CREATE TRIGGER {table.name}_no_{operation.lower()} "
            f"BEFORE {operation} ON {table.name} "
            f"BEGIN SELECT RAISE(ABORT, '{table.name} is append-only'); END"
        ).execute_if(dialect="sqlite")
        event.listen(table, "after_create", ddl)

class IdempotencyKey(Base):
    """Remembers which entry a save created, so a retried save can't post twice."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_idem_user_key"),
        CheckConstraint(
            "scope IN ('ISSUE', 'RECEIPT', 'OLD_GOLD')", name="ck_idem_scope"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    key: Mapped[str] = mapped_column(String(64))
    scope: Mapped[str] = mapped_column(String(12))
    request_hash: Mapped[str] = mapped_column(String(64))
    ref: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )




_make_append_only(LedgerEntry.__table__)
_make_append_only(AuditLog.__table__)
_make_append_only(StockEntry.__table__)
_make_append_only(OldGoldPurchase.__table__)
_make_append_only(OldGoldVoid.__table__)
_make_append_only(IdempotencyKey.__table__)