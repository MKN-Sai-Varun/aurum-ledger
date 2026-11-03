"""Corrections by reversal, and the per-karigar ledger view."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record
from app.db import get_session
from app.deps import current_user, require_roles
from app.domain.gold_math import format_pct, format_weight_g
from app.ledger import next_number, today_ist
from app.models import (
    KIND_ISSUE,
    KIND_REVERSAL,
    ROLE_FINANCE_HEAD,
    Job,
    Karigar,
    LedgerEntry,
    User,
)
from app.routers.jobs import JobOut, _job_outs

router = APIRouter(prefix="/api", tags=["corrections"])

MAX_LEDGER_ROWS = 500


def _signed_g(mg: int) -> str:
    text = format_weight_g(mg)
    return f"+{text}" if mg > 0 else text


class ReverseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=5, max_length=150)

    @field_validator("reason", mode="before")
    @classmethod
    def tidy_reason(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value


class ReversalOut(BaseModel):
    txn_no: str
    reverses_txn_no: str
    reversed_kind: str
    entry_date: date
    fine_weight_g: str
    change_g: str
    reason: str
    job: JobOut


class LedgerRow(BaseModel):
    txn_no: str
    entry_date: date
    job_no: str
    kind: str
    gross_weight_g: str
    purity_pct: str
    fine_weight_g: str
    change_g: str
    balance_g: str
    huid: str | None
    note: str | None
    reverses: str | None
    reversed_by: str | None


class LedgerOut(BaseModel):
    karigar_id: int
    karigar: str
    date_from: date | None
    date_to: date | None
    opening_balance_g: str
    closing_balance_g: str
    entries: list[LedgerRow]
    truncated: bool


@router.post("/entries/{txn_no}/reverse", response_model=ReversalOut, status_code=201)
def reverse_entry(
    txn_no: str,
    body: ReverseIn,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(ROLE_FINANCE_HEAD)),
):
    original = db.scalar(
        select(LedgerEntry).where(LedgerEntry.txn_no == txn_no.strip().upper())
    )
    if original is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    if original.kind == KIND_REVERSAL:
        raise HTTPException(
            status_code=409,
            detail="A reversal can't be reversed. Record a new entry instead.",
        )

    original_id = original.id
    original_txn = original.txn_no
    original_kind = original.kind
    karigar_id = original.karigar_id
    job_id = original.job_id
    gross_mg = original.gross_mg
    purity = original.purity_hundredths
    fine = original.fine_mg
    rate = original.wastage_hundredths
    change = -original.balance_delta_mg
    original_date = original.entry_date
    user_id = user.id

    if db.scalar(select(LedgerEntry.id).where(LedgerEntry.reverses_entry_id == original_id)):
        raise HTTPException(status_code=409, detail="This entry has already been reversed.")

    outstanding = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.balance_delta_mg), 0)).where(
            LedgerEntry.job_id == job_id
        )
    )
    if outstanding + change < 0:
        raise HTTPException(
            status_code=409,
            detail="This issue has receipts against it. Reverse those receipts first.",
        )

    entry_date = max(today_ist(), original_date)

    for _ in range(3):
        try:
            reversal = LedgerEntry(
                txn_no=next_number(db, LedgerEntry.txn_no, "TX-", 30001),
                entry_date=entry_date,
                karigar_id=karigar_id,
                job_id=job_id,
                kind=KIND_REVERSAL,
                gross_mg=gross_mg,
                purity_hundredths=purity,
                fine_mg=fine,
                wastage_hundredths=rate,
                balance_delta_mg=change,
                huid=None,
                note=f"Reverses {original_txn}: {body.reason}",
                reverses_entry_id=original_id,
                created_by=user_id,
            )
            db.add(reversal)
            db.flush()

            job = db.get(Job, job_id)
            closed_note = ""
            if original_kind == KIND_ISSUE and job.status == "OPEN":
                job.status = "CLOSED"
                job.closed_on = max(entry_date, job.opened_on)
                closed_note = ", job closed"

            record(
                db,
                user_id,
                "entry.reversed",
                "ledger_entry",
                reversal.id,
                f"{reversal.txn_no} reverses {original_txn}{closed_note}: {body.reason}",
            )
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            if db.scalar(
                select(LedgerEntry.id).where(LedgerEntry.reverses_entry_id == original_id)
            ):
                raise HTTPException(
                    status_code=409, detail="This entry has already been reversed."
                )
    else:
        raise HTTPException(status_code=503, detail="Couldn't save the reversal. Try again.")

    job = db.get(Job, job_id)
    return ReversalOut(
        txn_no=reversal.txn_no,
        reverses_txn_no=original_txn,
        reversed_kind=original_kind,
        entry_date=reversal.entry_date,
        fine_weight_g=format_weight_g(fine),
        change_g=_signed_g(change),
        reason=body.reason,
        job=_job_outs(db, [job], True)[0],
    )


@router.get("/karigars/{karigar_id}/ledger", response_model=LedgerOut)
def karigar_ledger(
    karigar_id: int,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=200, ge=1, le=MAX_LEDGER_ROWS),
    db: Session = Depends(get_session),
    _user: User = Depends(current_user),
):
    karigar = db.get(Karigar, karigar_id)
    if karigar is None:
        raise HTTPException(status_code=404, detail="Karigar not found.")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="The start date is after the end date.")

    entries = db.scalars(
        select(LedgerEntry)
        .where(LedgerEntry.karigar_id == karigar_id)
        .order_by(LedgerEntry.entry_date, LedgerEntry.id)
    ).all()
    job_numbers = {
        job.id: job.job_no
        for job in db.scalars(
            select(Job).where(Job.id.in_(list({e.job_id for e in entries}) or [0]))
        )
    }
    txn_by_id = {e.id: e.txn_no for e in entries}
    reversed_by = {
        e.reverses_entry_id: e.txn_no for e in entries if e.reverses_entry_id is not None
    }

    running = 0
    opening = 0
    rows: list[LedgerRow] = []
    for entry in entries:
        if date_to and entry.entry_date > date_to:
            break
        if date_from and entry.entry_date < date_from:
            running += entry.balance_delta_mg
            opening = running
            continue
        running += entry.balance_delta_mg
        rows.append(
            LedgerRow(
                txn_no=entry.txn_no,
                entry_date=entry.entry_date,
                job_no=job_numbers[entry.job_id],
                kind=entry.kind,
                gross_weight_g=format_weight_g(entry.gross_mg),
                purity_pct=format_pct(entry.purity_hundredths),
                fine_weight_g=format_weight_g(entry.fine_mg),
                change_g=_signed_g(entry.balance_delta_mg),
                balance_g=format_weight_g(running),
                huid=entry.huid,
                note=entry.note,
                reverses=txn_by_id.get(entry.reverses_entry_id),
                reversed_by=reversed_by.get(entry.id),
            )
        )

    return LedgerOut(
        karigar_id=karigar.id,
        karigar=karigar.name,
        date_from=date_from,
        date_to=date_to,
        opening_balance_g=format_weight_g(opening),
        closing_balance_g=format_weight_g(running),
        entries=rows[:limit],
        truncated=len(rows) > limit,
    )