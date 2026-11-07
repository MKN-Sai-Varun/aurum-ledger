from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record
from app.db import get_session
from app.deps import require_roles
from app.domain.closing_math import difference_mg, reconciles
from app.domain.gold_math import format_weight_g, parse_weight_g
from app.domain.stock_math import StockStatement
from app.ledger import today_ist
from app.models import (
    KIND_ISSUE,
    KIND_REVERSAL,
    ROLE_FINANCE_HEAD,
    STOCK_FROM_REFINER,
    STOCK_OPENING,
    STOCK_TO_REFINER,
    DayClose,
    LedgerEntry,
    OldGoldPurchase,
    OldGoldVoid,
    StockEntry,
    User,
)
from app.routers.corrections import _signed_g
from app.routers.stock import _compute

router = APIRouter(prefix="/api/closing", tags=["closing"])

MIN_NOTE = 5


class CloseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    close_date: date
    counted_vault: str = Field(min_length=1, max_length=12)
    note: str | None = Field(default=None, max_length=150)

    @field_validator("note", mode="before")
    @classmethod
    def tidy_note(cls, value):
        if isinstance(value, str):
            return " ".join(value.split()) or None
        return value


class Figures(BaseModel):
    total_g: str
    vault_g: str
    karigars_g: str
    refiner_g: str


class Movement(BaseModel):
    key: str
    label: str
    count: int
    effect_g: str


class ClosedOut(BaseModel):
    expected_vault_g: str
    counted_vault_g: str
    difference_g: str
    note: str | None
    by: str
    at: datetime
    changed_since_close: bool


class DayView(BaseModel):
    date: date
    opening: Figures
    movements: list[Movement]
    closing: Figures
    reconciles: bool
    consistent: bool
    closed: ClosedOut | None


class CloseRow(BaseModel):
    close_date: date
    expected_vault_g: str
    counted_vault_g: str
    difference_g: str
    note: str | None
    by: str


def _figures(s: StockStatement) -> Figures:
    return Figures(
        total_g=format_weight_g(s.total_mg),
        vault_g=format_weight_g(s.vault_mg),
        karigars_g=format_weight_g(s.karigars_mg),
        refiner_g=format_weight_g(s.refiner_mg),
    )


def _movements(db: Session, day: date) -> list[tuple[str, str, int, int]]:
    """Each movement of the day as (key, label, count, effect on the vault in mg)."""
    ledger = {
        kind: (count, fine, delta)
        for kind, count, fine, delta in db.execute(
            select(
                LedgerEntry.kind,
                func.count(),
                func.coalesce(func.sum(LedgerEntry.fine_mg), 0),
                func.coalesce(func.sum(LedgerEntry.balance_delta_mg), 0),
            )
            .where(LedgerEntry.entry_date == day)
            .group_by(LedgerEntry.kind)
        ).all()
    }
    issued_n, issued_fine, _issue_delta = ledger.get(KIND_ISSUE, (0, 0, 0))
    reversal_n, _reversal_fine, reversal_delta = ledger.get(KIND_REVERSAL, (0, 0, 0))
    returned = [v for k, v in ledger.items() if k not in (KIND_ISSUE, KIND_REVERSAL)]
    returned_n = sum(v[0] for v in returned)
    returned_fine = sum(v[1] for v in returned)

    bought_n, bought_fine = db.execute(
        select(func.count(), func.coalesce(func.sum(OldGoldPurchase.fine_mg), 0)).where(
            OldGoldPurchase.entry_date == day
        )
    ).one()
    voided_n, voided_fine = db.execute(
        select(func.count(), func.coalesce(func.sum(OldGoldPurchase.fine_mg), 0))
        .select_from(OldGoldPurchase)
        .join(OldGoldVoid, OldGoldVoid.purchase_id == OldGoldPurchase.id)
        .where(OldGoldVoid.voided_on == day)
    ).one()

    stock = {
        kind: (count, fine)
        for kind, count, fine in db.execute(
            select(
                StockEntry.kind,
                func.count(),
                func.coalesce(func.sum(StockEntry.fine_mg), 0),
            )
            .where(StockEntry.entry_date == day)
            .group_by(StockEntry.kind)
        ).all()
    }
    opening_n, opening_fine = stock.get(STOCK_OPENING, (0, 0))
    sent_n, sent_fine = stock.get(STOCK_TO_REFINER, (0, 0))
    received_n, received_fine = stock.get(STOCK_FROM_REFINER, (0, 0))

    lines: list[tuple[str, str, int, int]] = []
    if opening_n:
        lines.append(("opening_added", "Opening stock added", opening_n, opening_fine))
    lines += [
        ("issued", "Issued to karigars", issued_n, -issued_fine),
        ("returned", "Returned by karigars", returned_n, returned_fine),
        ("corrections", "Corrections by reversal", reversal_n, -reversal_delta),
        ("old_gold", "Old gold bought", bought_n, bought_fine),
        ("old_gold_void", "Old gold voided", voided_n, -voided_fine),
        ("to_refiner", "Sent to refiner", sent_n, -sent_fine),
        ("from_refiner", "Received from refiner", received_n, received_fine),
    ]
    return lines


def _build(db: Session, day: date):
    opening, _ = _compute(db, day - timedelta(days=1))
    closing, _ = _compute(db, day)
    lines = _movements(db, day)
    effects = [effect for _key, _label, _count, effect in lines]
    balanced = reconciles(opening.vault_mg, effects, closing.vault_mg)

    found = db.execute(
        select(DayClose, User.full_name)
        .join(User, User.id == DayClose.closed_by)
        .where(DayClose.close_date == day)
    ).first()
    closed = None
    if found:
        row, name = found
        changed = (row.total_mg, row.karigars_mg, row.refiner_mg, row.expected_vault_mg) != (
            closing.total_mg,
            closing.karigars_mg,
            closing.refiner_mg,
            closing.vault_mg,
        )
        closed = ClosedOut(
            expected_vault_g=format_weight_g(row.expected_vault_mg),
            counted_vault_g=format_weight_g(row.counted_vault_mg),
            difference_g=_signed_g(row.difference_mg),
            note=row.note,
            by=name,
            at=row.created_at,
            changed_since_close=changed,
        )

    view = DayView(
        date=day,
        opening=_figures(opening),
        movements=[
            Movement(key=key, label=label, count=count, effect_g=_signed_g(effect))
            for key, label, count, effect in lines
        ],
        closing=_figures(closing),
        reconciles=balanced,
        consistent=closing.consistent,
        closed=closed,
    )
    return view, opening, closing


def _check_day(day: date) -> None:
    if day > today_ist():
        raise HTTPException(status_code=422, detail="The date can't be in the future.")


@router.get("/day", response_model=DayView)
def day_view(
    day: date | None = Query(default=None, alias="date"),
    db: Session = Depends(get_session),
    _user: User = Depends(require_roles(ROLE_FINANCE_HEAD)),
):
    chosen = day or today_ist()
    _check_day(chosen)
    return _build(db, chosen)[0]


@router.get("/history", response_model=list[CloseRow])
def history(
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_session),
    _user: User = Depends(require_roles(ROLE_FINANCE_HEAD)),
):
    rows = db.execute(
        select(DayClose, User.full_name)
        .join(User, User.id == DayClose.closed_by)
        .order_by(DayClose.close_date.desc())
        .limit(limit)
    ).all()
    return [
        CloseRow(
            close_date=row.close_date,
            expected_vault_g=format_weight_g(row.expected_vault_mg),
            counted_vault_g=format_weight_g(row.counted_vault_mg),
            difference_g=_signed_g(row.difference_mg),
            note=row.note,
            by=name,
        )
        for row, name in rows
    ]


@router.post("/close", response_model=DayView, status_code=201)
def close_day(
    body: CloseIn,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(ROLE_FINANCE_HEAD)),
):
    day = body.close_date
    _check_day(day)
    if db.scalar(select(DayClose.id).where(DayClose.close_date == day)):
        raise HTTPException(status_code=409, detail="This day has already been closed.")
    try:
        counted = parse_weight_g(body.counted_vault)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail="Enter the counted vault weight in grams with up to 3 decimals.",
        )

    view, opening, closing = _build(db, day)
    if not closing.consistent:
        raise HTTPException(
            status_code=409,
            detail="More gold is recorded as out of the vault than was ever in it. Check the stock first.",
        )
    if not view.reconciles:
        raise HTTPException(
            status_code=409,
            detail="The day's movements don't add up to the closing figures, so it can't be closed.",
        )

    difference = difference_mg(counted, closing.vault_mg)
    if difference != 0 and (body.note is None or len(body.note) < MIN_NOTE):
        raise HTTPException(
            status_code=422,
            detail=f"The count differs from the records. Add a note of at least {MIN_NOTE} characters.",
        )

    user_id = user.id
    try:
        row = DayClose(
            close_date=day,
            opening_vault_mg=opening.vault_mg,
            expected_vault_mg=closing.vault_mg,
            counted_vault_mg=counted,
            difference_mg=difference,
            total_mg=closing.total_mg,
            karigars_mg=closing.karigars_mg,
            refiner_mg=closing.refiner_mg,
            note=body.note,
            closed_by=user_id,
        )
        db.add(row)
        db.flush()
        detail = (
            f"{day.isoformat()} expected {format_weight_g(closing.vault_mg)} g, "
            f"counted {format_weight_g(counted)} g, difference {_signed_g(difference)} g"
        )
        if body.note:
            detail += f": {body.note}"
        record(db, user_id, "day.closed", "day_close", row.id, detail)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This day has already been closed.")

    return _build(db, day)[0]