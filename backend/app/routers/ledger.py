from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record
from app.db import get_session
from app.deps import current_user, require_roles
from app.domain.gold_math import (
    allowed_wastage_mg,
    fine_weight_mg,
    format_pct,
    format_weight_g,
    parse_purity_pct,
    parse_weight_g,
)
from app.ledger import karigar_balance_mg, next_number, today_ist
from app.models import (
    KIND_ISSUE,
    ROLE_ISSUE_CLERK,
    ItemCategory,
    Job,
    Karigar,
    KarigarWastage,
    LedgerEntry,
    User,
)

router = APIRouter(prefix="/api", tags=["ledger"])

MAX_ISSUE_MG = 2_000_000  # 2000.000 g, a typo guard
BACKDATE_DAYS = 7
WEIGHT_HELP = "Enter a weight in grams with up to 3 decimals."
PURITY_HELP = "Enter a purity above 0 and up to 100, with up to 2 decimals."


class IssueIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    karigar_id: StrictInt = Field(gt=0)
    category_id: StrictInt = Field(gt=0)
    gross_weight: str = Field(min_length=1, max_length=12)
    purity: str = Field(min_length=1, max_length=8)
    entry_date: date | None = None
    note: str | None = Field(default=None, max_length=200)

    @field_validator("note", mode="before")
    @classmethod
    def tidy_note(cls, value):
        if isinstance(value, str):
            return " ".join(value.split()) or None
        return value


class SlipOut(BaseModel):
    txn_no: str
    job_no: str
    entry_date: date
    karigar_id: int
    karigar: str
    category: str
    gross_weight_g: str
    purity_pct: str
    fine_weight_g: str
    allowed_wastage_pct: str
    allowed_wastage_g: str
    balance_g: str  # the karigar's balance at the moment the slip is viewed
    note: str | None
    issued_by: str


class BalanceOut(BaseModel):
    karigar_id: int
    karigar: str
    as_of: date
    balance_g: str


def _slip(db: Session, entry: LedgerEntry) -> SlipOut:
    karigar = db.get(Karigar, entry.karigar_id)
    job = db.get(Job, entry.job_id)
    category = db.get(ItemCategory, job.category_id)
    issuer = db.get(User, entry.created_by)
    return SlipOut(
        txn_no=entry.txn_no,
        job_no=job.job_no,
        entry_date=entry.entry_date,
        karigar_id=karigar.id,
        karigar=karigar.name,
        category=category.name,
        gross_weight_g=format_weight_g(entry.gross_mg),
        purity_pct=format_pct(entry.purity_hundredths),
        fine_weight_g=format_weight_g(entry.fine_mg),
        allowed_wastage_pct=format_pct(entry.wastage_hundredths),
        allowed_wastage_g=format_weight_g(
            allowed_wastage_mg(entry.fine_mg, entry.wastage_hundredths)
        ),
        balance_g=format_weight_g(karigar_balance_mg(db, karigar.id)),
        note=entry.note,
        issued_by=issuer.full_name,
    )




@router.post("/issues", response_model=SlipOut, status_code=201)
def create_issue(
    body: IssueIn,
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
    if gross_mg > MAX_ISSUE_MG:
        raise HTTPException(
            status_code=422,
            detail=f"A single issue can't be more than {format_weight_g(MAX_ISSUE_MG)} g.",
        )
    fine = fine_weight_mg(gross_mg, purity)
    if fine <= 0:
        raise HTTPException(
            status_code=422,
            detail="That weight and purity give no fine gold. Check both values.",
        )

    today = today_ist()
    entry_date = body.entry_date or today
    if entry_date > today:
        raise HTTPException(status_code=422, detail="The date can't be in the future.")
    if entry_date < today - timedelta(days=BACKDATE_DAYS):
        raise HTTPException(
            status_code=422,
            detail=f"The date can't be more than {BACKDATE_DAYS} days ago.",
        )

    karigar = db.get(Karigar, body.karigar_id)
    if karigar is None:
        raise HTTPException(status_code=404, detail="Karigar not found.")
    if not karigar.is_active:
        raise HTTPException(status_code=409, detail="This karigar is inactive.")
    category = db.get(ItemCategory, body.category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Item category not found.")

    rate = db.scalar(
        select(KarigarWastage.wastage_hundredths).where(
            KarigarWastage.karigar_id == karigar.id,
            KarigarWastage.category_id == category.id,
        )
    )
    if rate is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "No agreed wastage is set for this karigar and item category. "
                "Ask the finance head to set it."
            ),
        )

    user_id, karigar_id, category_id = user.id, karigar.id, category.id
    karigar_name = karigar.name

    for _ in range(3):
        try:
            job = Job(
                job_no=next_number(db, Job.job_no, "JOB-", 1001),
                karigar_id=karigar_id,
                category_id=category_id,
                status="OPEN",
                opened_on=entry_date,
                created_by=user_id,
            )
            db.add(job)
            db.flush()
            entry = LedgerEntry(
                txn_no=next_number(db, LedgerEntry.txn_no, "TX-", 30001),
                entry_date=entry_date,
                karigar_id=karigar_id,
                job_id=job.id,
                kind=KIND_ISSUE,
                gross_mg=gross_mg,
                purity_hundredths=purity,
                fine_mg=fine,
                wastage_hundredths=rate,
                balance_delta_mg=fine,
                note=body.note,
                created_by=user_id,
            )
            db.add(entry)
            db.flush()
            record(
                db,
                user_id,
                "issue.created",
                "ledger_entry",
                entry.id,
                f"{entry.txn_no} {job.job_no} {karigar_name} fine {format_weight_g(fine)} g",
            )
            db.commit()
            return _slip(db, entry)
        except IntegrityError:
            db.rollback()
    raise HTTPException(status_code=503, detail="Couldn't save the issue. Try again.")


@router.get("/issues/{txn_no}", response_model=SlipOut)
def get_issue(
    txn_no: str,
    db: Session = Depends(get_session),
    _user: User = Depends(current_user),
):
    entry = db.scalar(
        select(LedgerEntry).where(
            LedgerEntry.txn_no == txn_no, LedgerEntry.kind == KIND_ISSUE
        )
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Issue not found.")
    return _slip(db, entry)


@router.get("/karigars/{karigar_id}/balance", response_model=BalanceOut)
def get_balance(
    karigar_id: int,
    as_of: date | None = None,
    db: Session = Depends(get_session),
    _user: User = Depends(current_user),
):
    karigar = db.get(Karigar, karigar_id)
    if karigar is None:
        raise HTTPException(status_code=404, detail="Karigar not found.")
    day = as_of or today_ist()
    return BalanceOut(
        karigar_id=karigar.id,
        karigar=karigar.name,
        as_of=day,
        balance_g=format_weight_g(karigar_balance_mg(db, karigar.id, day)),
    )