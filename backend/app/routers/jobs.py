"""Jobs and receipts.

A job is one batch of gold issued to a karigar. Receipts return fine gold
against it, and closing the job fixes the comparison of what is still
outstanding with the agreed wastage.
"""
import re
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.audit import record
from app.db import get_session
from app.deps import current_user, require_roles
from app.domain.gold_math import (
    fine_weight_mg,
    format_pct,
    format_weight_g,
    parse_purity_pct,
    parse_weight_g,
)
from app.domain.job_math import JobSummary, needs_review, summarise_job
from app.ledger import next_number, today_ist
from app.models import (
    KIND_ISSUE,
    KIND_RECEIPT_FILINGS,
    KIND_RECEIPT_PIECE,
    KIND_RECEIPT_SCRAP,
    ROLE_FINANCE_HEAD,
    ROLE_ISSUE_CLERK,
    ItemCategory,
    Job,
    Karigar,
    LedgerEntry,
    User,
)

router = APIRouter(prefix="/api", tags=["jobs"])

MAX_RECEIPT_MG = 2_000_000  # 2000.000 g, a typo guard
BACKDATE_DAYS = 7
HUID_RE = re.compile(r"[A-Z0-9]{6,12}")
WEIGHT_HELP = "Enter a weight in grams with up to 3 decimals."
PURITY_HELP = "Enter a purity above 0 and up to 100, with up to 2 decimals."

RECEIPT_KINDS = {
    "PIECE": KIND_RECEIPT_PIECE,
    "SCRAP": KIND_RECEIPT_SCRAP,
    "FILINGS": KIND_RECEIPT_FILINGS,
}
def _reversed_ids():
    """Ids of ledger entries that have been reversed. Aliased to avoid auto-correlation."""
    reversal = aliased(LedgerEntry)
    return select(reversal.reverses_entry_id).where(
        reversal.reverses_entry_id.is_not(None)
    )

class ReceiptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_no: str = Field(min_length=1, max_length=20)
    kind: Literal["PIECE", "SCRAP", "FILINGS"]
    gross_weight: str = Field(min_length=1, max_length=12)
    purity: str = Field(min_length=1, max_length=8)
    huid: str | None = Field(default=None, max_length=12)
    entry_date: date | None = None
    note: str | None = Field(default=None, max_length=200)

    @field_validator("job_no", mode="before")
    @classmethod
    def tidy_job_no(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("huid", mode="before")
    @classmethod
    def tidy_huid(cls, value):
        if isinstance(value, str):
            return value.strip().upper() or None
        return value

    @field_validator("note", mode="before")
    @classmethod
    def tidy_note(cls, value):
        if isinstance(value, str):
            return " ".join(value.split()) or None
        return value


class JobOut(BaseModel):
    job_no: str
    karigar_id: int
    karigar: str
    category: str
    status: str
    opened_on: date
    closed_on: date | None
    issued_fine_g: str
    returned_fine_g: str
    outstanding_g: str
    allowed_wastage_pct: str
    allowed_wastage_g: str
    # Finance head only. None for the issue clerk.
    unexplained_g: str | None
    review: bool | None


class EntryOut(BaseModel):
    txn_no: str
    kind: str
    entry_date: date
    gross_weight_g: str
    purity_pct: str
    fine_weight_g: str
    huid: str | None
    note: str | None


class JobDetail(JobOut):
    entries: list[EntryOut]


class ReceiptOut(BaseModel):
    txn_no: str
    kind: str
    entry_date: date
    gross_weight_g: str
    purity_pct: str
    fine_weight_g: str
    huid: str | None
    note: str | None
    job: JobOut


def _summaries(db: Session, jobs: list[Job]) -> dict[int, JobSummary]:
    ids = [job.id for job in jobs]
    if not ids:
        return {}
    rows = db.execute(
        select(
            LedgerEntry.job_id,
                        func.coalesce(
                func.sum(
                    case(
                        (
                            (LedgerEntry.kind == KIND_ISSUE)
                            & LedgerEntry.id.not_in(_reversed_ids()),
                            LedgerEntry.fine_mg,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(func.sum(LedgerEntry.balance_delta_mg), 0),
            func.coalesce(func.max(LedgerEntry.wastage_hundredths), 0),
        )
        .where(LedgerEntry.job_id.in_(ids))
        .group_by(LedgerEntry.job_id)
    ).all()
    return {
        job_id: summarise_job(
            issued_fine_mg=issued,
            wastage_hundredths=rate,
            outstanding_mg=outstanding,
        )
        for job_id, issued, outstanding, rate in rows
    }


def _job_outs(db: Session, jobs: list[Job], show_review: bool) -> list[JobOut]:
    if not jobs:
        return []
    summaries = _summaries(db, jobs)
    karigars = {
        k.id: k.name
        for k in db.scalars(
            select(Karigar).where(Karigar.id.in_(list({j.karigar_id for j in jobs})))
        )
    }
    categories = {
        c.id: c.name
        for c in db.scalars(
            select(ItemCategory).where(ItemCategory.id.in_(list({j.category_id for j in jobs})))
        )
    }
    result = []
    for job in jobs:
        s = summaries.get(job.id) or summarise_job(0, 0, 0)
        result.append(
            JobOut(
                job_no=job.job_no,
                karigar_id=job.karigar_id,
                karigar=karigars[job.karigar_id],
                category=categories[job.category_id],
                status=job.status,
                opened_on=job.opened_on,
                closed_on=job.closed_on,
                issued_fine_g=format_weight_g(s.issued_mg),
                returned_fine_g=format_weight_g(s.returned_mg),
                outstanding_g=format_weight_g(s.outstanding_mg),
                allowed_wastage_pct=format_pct(s.wastage_hundredths),
                allowed_wastage_g=format_weight_g(s.allowed_mg),
                unexplained_g=format_weight_g(s.unexplained_mg) if show_review else None,
                review=needs_review(job.status, s.unexplained_mg) if show_review else None,
            )
        )
    return result


def _get_job(db: Session, job_no: str) -> Job:
    job = db.scalar(select(Job).where(Job.job_no == job_no.strip().upper()))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    status: Literal["OPEN", "CLOSED"] | None = None,
    karigar_id: int | None = None,
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    query = select(Job).order_by(Job.opened_on.desc(), Job.id.desc())
    if status is not None:
        query = query.where(Job.status == status)
    if karigar_id is not None:
        query = query.where(Job.karigar_id == karigar_id)
    return _job_outs(db, list(db.scalars(query)), user.role == ROLE_FINANCE_HEAD)


@router.get("/jobs/{job_no}", response_model=JobDetail)
def get_job(
    job_no: str,
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    job = _get_job(db, job_no)
    base = _job_outs(db, [job], user.role == ROLE_FINANCE_HEAD)[0]
    entries = db.scalars(
        select(LedgerEntry)
        .where(LedgerEntry.job_id == job.id)
        .order_by(LedgerEntry.entry_date, LedgerEntry.id)
    ).all()
    return JobDetail(
        **base.model_dump(),
        entries=[
            EntryOut(
                txn_no=e.txn_no,
                kind=e.kind,
                entry_date=e.entry_date,
                gross_weight_g=format_weight_g(e.gross_mg),
                purity_pct=format_pct(e.purity_hundredths),
                fine_weight_g=format_weight_g(e.fine_mg),
                huid=e.huid,
                note=e.note,
            )
            for e in entries
        ],
    )


@router.post("/jobs/{job_no}/close", response_model=JobOut)
def close_job(
    job_no: str,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(ROLE_ISSUE_CLERK)),
):
    job = _get_job(db, job_no)
    if job.status != "OPEN":
        raise HTTPException(status_code=409, detail="This job is already closed.")
    summary = _summaries(db, [job]).get(job.id) or summarise_job(0, 0, 0)
    job.status = "CLOSED"
    job.closed_on = max(today_ist(), job.opened_on)
    record(
        db,
        user.id,
        "job.closed",
        "job",
        job.id,
        f"{job.job_no} closed, outstanding {format_weight_g(summary.outstanding_mg)} g, "
        f"allowed {format_weight_g(summary.allowed_mg)} g",
    )
    db.commit()
    return _job_outs(db, [job], False)[0]


@router.post("/receipts", response_model=ReceiptOut, status_code=201)
def create_receipt(
    body: ReceiptIn,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(ROLE_ISSUE_CLERK)),
):
    try:
        gross_mg = parse_weight_g(body.gross_weight)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail=WEIGHT_HELP)
    try:
        purity = parse_purity_pct(body.purity)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail=PURITY_HELP)

    if gross_mg <= 0:
        raise HTTPException(status_code=422, detail="The weight must be above 0.")
    if gross_mg > MAX_RECEIPT_MG:
        raise HTTPException(
            status_code=422,
            detail=f"A single receipt can't be more than {format_weight_g(MAX_RECEIPT_MG)} g.",
        )
    fine = fine_weight_mg(gross_mg, purity)
    if fine <= 0:
        raise HTTPException(
            status_code=422,
            detail="That weight and purity give no fine gold. Check both values.",
        )

    if body.kind == "PIECE":
        if body.huid is None:
            raise HTTPException(status_code=422, detail="A finished piece needs its HUID.")
        if not HUID_RE.fullmatch(body.huid):
            raise HTTPException(
                status_code=422, detail="The HUID must be 6 to 12 letters or digits."
            )
    elif body.huid is not None:
        raise HTTPException(status_code=422, detail="Only finished pieces have a HUID.")

    job = _get_job(db, body.job_no)
    if job.status != "OPEN":
        raise HTTPException(status_code=409, detail="This job is closed.")

    if body.huid is not None and db.scalar(
        select(LedgerEntry.id).where(
            LedgerEntry.huid == body.huid,
            LedgerEntry.id.not_in(_reversed_ids()),
        )
    ):
        raise HTTPException(status_code=409, detail="That HUID is already recorded.")

    today = today_ist()
    entry_date = body.entry_date or today
    if entry_date > today:
        raise HTTPException(status_code=422, detail="The date can't be in the future.")
    if entry_date < today - timedelta(days=BACKDATE_DAYS):
        raise HTTPException(
            status_code=422,
            detail=f"The date can't be more than {BACKDATE_DAYS} days ago.",
        )
    if entry_date < job.opened_on:
        raise HTTPException(
            status_code=422,
            detail=f"The date can't be before the job was opened on {job.opened_on.isoformat()}.",
        )

    outstanding = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.balance_delta_mg), 0)).where(
            LedgerEntry.job_id == job.id
        )
    )
    if fine > outstanding:
        raise HTTPException(
            status_code=422,
            detail=(
                f"That is {format_weight_g(fine)} g of fine gold, but only "
                f"{format_weight_g(outstanding)} g is outstanding on {job.job_no}."
            ),
        )

    rate = db.scalar(
        select(LedgerEntry.wastage_hundredths).where(
            LedgerEntry.job_id == job.id, LedgerEntry.kind == KIND_ISSUE
        )
    )
    if rate is None:
        raise HTTPException(status_code=409, detail="This job has no issue entry.")

    job_id, job_no, karigar_id, user_id = job.id, job.job_no, job.karigar_id, user.id
    kind = RECEIPT_KINDS[body.kind]

    for _ in range(3):
        try:
            entry = LedgerEntry(
                txn_no=next_number(db, LedgerEntry.txn_no, "TX-", 30001),
                entry_date=entry_date,
                karigar_id=karigar_id,
                job_id=job_id,
                kind=kind,
                gross_mg=gross_mg,
                purity_hundredths=purity,
                fine_mg=fine,
                wastage_hundredths=rate,
                balance_delta_mg=-fine,
                huid=body.huid,
                note=body.note,
                created_by=user_id,
            )
            db.add(entry)
            db.flush()
            record(
                db,
                user_id,
                "receipt.created",
                "ledger_entry",
                entry.id,
                f"{entry.txn_no} {job_no} {body.kind} fine {format_weight_g(fine)} g",
            )
            db.commit()
            break
        except IntegrityError:
            db.rollback()
    else:
        raise HTTPException(status_code=503, detail="Couldn't save the receipt. Try again.")

    job = db.get(Job, job_id)
    return ReceiptOut(
        txn_no=entry.txn_no,
        kind=entry.kind,
        entry_date=entry.entry_date,
        gross_weight_g=format_weight_g(gross_mg),
        purity_pct=format_pct(purity),
        fine_weight_g=format_weight_g(fine),
        huid=entry.huid,
        note=entry.note,
        job=_job_outs(db, [job], False)[0],
    )