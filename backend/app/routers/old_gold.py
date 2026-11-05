import re
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record
from app.idempotency import begin
from app.db import get_session
from app.deps import current_user, require_roles
from app.domain.gold_math import (
    fine_weight_mg,
    format_pct,
    format_weight_g,
    parse_purity_pct,
    parse_weight_g,
)
from app.domain.old_gold_math import (
    HIGH_VALUE_PAISE,
    MAX_RATE_PAISE,
    PAN_RE,
    format_rupees,
    is_high_value,
    mask_pan,
    parse_rupees,
    value_paise,
)
from app.ledger import next_number, today_ist
from app.models import (
    PAY_ADJUSTED,
    PAY_BANK,
    PAY_CASH,
    PAY_CHEQUE,
    PAY_UPI,
    ROLE_FINANCE_HEAD,
    ROLE_ISSUE_CLERK,
    OldGoldPurchase,
    OldGoldVoid,
    User,
)
from app.readings_check import ReadingFields, apply_readings, check_readings

router = APIRouter(prefix="/api", tags=["old-gold"])

MAX_GROSS_MG = 2_000_000  # 2000.000 g, a typo guard
BACKDATE_DAYS = 7
BILL_RE = re.compile(r"[A-Z0-9][A-Z0-9/_.-]{2,29}")
WEIGHT_HELP = "Enter a weight in grams with up to 3 decimals."
PURITY_HELP = "Enter a purity above 0 and up to 100, with up to 2 decimals."

PAYMENT_LABELS = {
    PAY_CASH: "Cash",
    PAY_BANK: "Bank transfer",
    PAY_UPI: "UPI",
    PAY_CHEQUE: "Cheque",
    PAY_ADJUSTED: "Adjusted against the new bill",
}


class OldGoldIn(ReadingFields):
    model_config = ConfigDict(extra="forbid")
    bill_no: str = Field(min_length=3, max_length=30)
    customer_name: str = Field(min_length=2, max_length=100)
    gross_weight: str = Field(min_length=1, max_length=12)
    deduction_weight: str = Field(default="0", min_length=1, max_length=12)
    purity: str = Field(min_length=1, max_length=8)
    rate_per_g: str = Field(min_length=1, max_length=12)
    payment_mode: Literal["CASH", "BANK_TRANSFER", "UPI", "CHEQUE", "ADJUSTED"]
    pan: str | None = Field(default=None, max_length=10)
    entry_date: date | None = None
    note: str | None = Field(default=None, max_length=200)

    @field_validator("bill_no", mode="before")
    @classmethod
    def tidy_bill(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("customer_name", mode="before")
    @classmethod
    def tidy_name(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("pan", mode="before")
    @classmethod
    def tidy_pan(cls, value):
        if isinstance(value, str):
            return value.strip().upper() or None
        return value

    @field_validator("note", mode="before")
    @classmethod
    def tidy_note(cls, value):
        if isinstance(value, str):
            return " ".join(value.split()) or None
        return value


class VoidIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=5, max_length=150)

    @field_validator("reason", mode="before")
    @classmethod
    def tidy_reason(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value


class PurchaseOut(BaseModel):
    og_no: str
    entry_date: date
    bill_no: str
    customer_name: str
    gross_weight_g: str
    deduction_g: str
    net_weight_g: str
    purity_pct: str
    fine_weight_g: str
    rate_per_g: str
    value: str
    payment_mode: str
    payment_label: str
    pan: str | None
    pan_masked: bool
    high_value: bool
    # Finance head only. None for the issue clerk.
    needs_review: bool | None
    note: str | None
    recorded_by: str
    voided: bool
    void_reason: str | None


def _out(
    db: Session,
    purchase: OldGoldPurchase,
    role: str,
    void: OldGoldVoid | None,
    show_full_pan: bool,
) -> PurchaseOut:
    recorder = db.get(User, purchase.created_by)
    high = is_high_value(purchase.value_paise)
    pan = purchase.pan
    full = show_full_pan and role == ROLE_FINANCE_HEAD
    return PurchaseOut(
        og_no=purchase.og_no,
        entry_date=purchase.entry_date,
        bill_no=purchase.bill_no,
        customer_name=purchase.customer_name,
        gross_weight_g=format_weight_g(purchase.gross_mg),
        deduction_g=format_weight_g(purchase.deduction_mg),
        net_weight_g=format_weight_g(purchase.gross_mg - purchase.deduction_mg),
        purity_pct=format_pct(purchase.purity_hundredths),
        fine_weight_g=format_weight_g(purchase.fine_mg),
        rate_per_g=format_rupees(purchase.rate_paise),
        value=format_rupees(purchase.value_paise),
        payment_mode=purchase.payment_mode,
        payment_label=PAYMENT_LABELS[purchase.payment_mode],
        pan=pan if (full or pan is None) else mask_pan(pan),
        pan_masked=pan is not None and not full,
        high_value=high,
        needs_review=(
            (high and purchase.payment_mode == PAY_CASH and void is None)
            if role == ROLE_FINANCE_HEAD
            else None
        ),
        note=purchase.note,
        recorded_by=recorder.full_name,
        voided=void is not None,
        void_reason=void.reason if void else None,
    )


def _get(db: Session, og_no: str) -> OldGoldPurchase:
    purchase = db.scalar(
        select(OldGoldPurchase).where(OldGoldPurchase.og_no == og_no.strip().upper())
    )
    if purchase is None:
        raise HTTPException(status_code=404, detail="Purchase not found.")
    return purchase


def _void_of(db: Session, purchase_id: int) -> OldGoldVoid | None:
    return db.scalar(select(OldGoldVoid).where(OldGoldVoid.purchase_id == purchase_id))


@router.post("/old-gold", response_model=PurchaseOut, status_code=201)
def create_purchase(
    body: OldGoldIn,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(ROLE_ISSUE_CLERK)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    idem = begin(
        db, user.id, idempotency_key, "OLD_GOLD", body.model_dump_json(),
        lambda ref: _out(db, _get(db, ref), ROLE_ISSUE_CLERK, None, show_full_pan=False),
    )
    try:
        gross = parse_weight_g(body.gross_weight)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail=WEIGHT_HELP)
    try:
        deduction = parse_weight_g(body.deduction_weight)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail="Enter the deduction as a weight in grams with up to 3 decimals, or 0.",
        )
    try:
        purity = parse_purity_pct(body.purity)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail=PURITY_HELP)
    try:
        rate = parse_rupees(body.rate_per_g)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail="Enter the rate in rupees per gram with up to 2 decimals.",
        )

    if gross <= 0:
        raise HTTPException(status_code=422, detail="The weight must be above 0.")
    if gross > MAX_GROSS_MG:
        raise HTTPException(
            status_code=422,
            detail=f"A single purchase can't be more than {format_weight_g(MAX_GROSS_MG)} g.",
        )
    if deduction >= gross:
        raise HTTPException(
            status_code=422,
            detail="The deduction must be less than the gross weight.",
        )
    if rate <= 0 or rate > MAX_RATE_PAISE:
        raise HTTPException(
            status_code=422,
            detail=f"The rate must be above 0 and at most {format_rupees(MAX_RATE_PAISE)} per gram.",
        )

    fine = fine_weight_mg(gross - deduction, purity)
    if fine <= 0:
        raise HTTPException(
            status_code=422,
            detail="That weight and purity give no fine gold. Check the values.",
        )
    value = value_paise(fine, rate)

    if body.pan is not None and not PAN_RE.fullmatch(body.pan):
        raise HTTPException(
            status_code=422,
            detail="The PAN must be 5 letters, 4 digits and 1 letter, for example ABCDE1234F.",
        )
    if is_high_value(value) and body.pan is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"A purchase of Rs {format_rupees(HIGH_VALUE_PAISE)} or more needs the "
                "customer's PAN."
            ),
        )
    if not BILL_RE.fullmatch(body.bill_no):
        raise HTTPException(
            status_code=422,
            detail="The bill reference must be 3 to 30 letters, digits or - / _ .",
        )

    existing = db.scalar(
        select(OldGoldPurchase.og_no).where(
            OldGoldPurchase.bill_no == body.bill_no,
            OldGoldPurchase.id.not_in(select(OldGoldVoid.purchase_id)),
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"This bill already has an old gold record ({existing}).",
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

    confirmations = check_readings(
        db, user, body, format_weight_g(gross), format_pct(purity)
    )

    user_id = user.id
    for _ in range(3):
        try:
            purchase = OldGoldPurchase(
                og_no=next_number(db, OldGoldPurchase.og_no, "OG-", 5001),
                entry_date=entry_date,
                bill_no=body.bill_no,
                customer_name=body.customer_name,
                gross_mg=gross,
                deduction_mg=deduction,
                purity_hundredths=purity,
                fine_mg=fine,
                rate_paise=rate,
                value_paise=value,
                payment_mode=body.payment_mode,
                pan=body.pan,
                note=body.note,
                created_by=user_id,
            )
            db.add(purchase)
            db.flush()
            record(
                db,
                user_id,
                "old_gold.created",
                "old_gold_purchase",
                purchase.id,
                f"{purchase.og_no} bill {purchase.bill_no} fine {format_weight_g(fine)} g "
                f"value Rs {format_rupees(value)} by {body.payment_mode}",
            )
            apply_readings(db, user_id, confirmations, purchase.og_no)
            idem.remember(db, purchase.og_no)
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            idem.raise_if_stored(db)
    else:
        raise HTTPException(status_code=503, detail="Couldn't save the purchase. Try again.")

    return _out(db, purchase, ROLE_ISSUE_CLERK, None, show_full_pan=False)


@router.get("/old-gold", response_model=list[PurchaseOut])
def list_purchases(
    bill: str | None = Query(default=None, max_length=30),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    query = select(OldGoldPurchase).order_by(
        OldGoldPurchase.entry_date.desc(), OldGoldPurchase.id.desc()
    )
    if bill and bill.strip():
        query = query.where(
            OldGoldPurchase.bill_no.contains(bill.strip().upper(), autoescape=True)
        )
    purchases = list(db.scalars(query.limit(limit)))
    voids = {
        v.purchase_id: v
        for v in db.scalars(
            select(OldGoldVoid).where(
                OldGoldVoid.purchase_id.in_([p.id for p in purchases] or [0])
            )
        )
    }
    return [_out(db, p, user.role, voids.get(p.id), show_full_pan=False) for p in purchases]


@router.get("/old-gold/{og_no}", response_model=PurchaseOut)
def get_purchase(
    og_no: str,
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    purchase = _get(db, og_no)
    return _out(db, purchase, user.role, _void_of(db, purchase.id), show_full_pan=True)


@router.post("/old-gold/{og_no}/void", response_model=PurchaseOut)
def void_purchase(
    og_no: str,
    body: VoidIn,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(ROLE_FINANCE_HEAD)),
):
    purchase = _get(db, og_no)
    if _void_of(db, purchase.id) is not None:
        raise HTTPException(status_code=409, detail="This purchase is already voided.")
    voided_on = max(today_ist(), purchase.entry_date)
    purchase_id, number, user_id = purchase.id, purchase.og_no, user.id
    try:
        db.add(
            OldGoldVoid(
                purchase_id=purchase_id,
                reason=body.reason,
                voided_on=voided_on,
                voided_by=user_id,
            )
        )
        db.flush()
        record(db, user_id, "old_gold.voided", "old_gold_purchase", purchase_id,
               f"{number}: {body.reason}")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This purchase is already voided.")
    purchase = db.get(OldGoldPurchase, purchase_id)
    return _out(db, purchase, user.role, _void_of(db, purchase_id), show_full_pan=True)