import csv
import io
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import record
from app.db import get_session
from app.deps import require_roles
from app.domain.gold_math import format_weight_g, parse_weight_g
from app.domain.stock_math import StockStatement, compute_statement
from app.ledger import today_ist
from app.models import (
    ROLE_FINANCE_HEAD,
    STOCK_FROM_REFINER,
    STOCK_OPENING,
    STOCK_TO_REFINER,
    Karigar,
    LedgerEntry,
    StockEntry,
    User,
    OldGoldPurchase,
    OldGoldVoid,
)

router = APIRouter(prefix="/api/stock", tags=["stock"])

MAX_REFINER_MG = 5_000_000  # 5000.000 g, a typo guard
BACKDATE_DAYS = 7
WEIGHT_HELP = "Enter a weight in grams with up to 3 decimals."
BASIS = (
    "Total stock is the opening stock plus old gold bought. "
    "Vault is the total less the gold with karigars and at the refiner."
)

LABELS = {
    STOCK_OPENING: "Opening stock",
    STOCK_TO_REFINER: "Sent to refiner",
    STOCK_FROM_REFINER: "Received from refiner",
}


class RefinerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    direction: Literal["SEND", "RECEIVE"]
    fine_weight: str = Field(min_length=1, max_length=12)
    entry_date: date | None = None
    note: str | None = Field(default=None, max_length=200)

    @field_validator("note", mode="before")
    @classmethod
    def tidy_note(cls, value):
        if isinstance(value, str):
            return " ".join(value.split()) or None
        return value


class HolderOut(BaseModel):
    karigar_id: int
    karigar: str
    balance_g: str


class StatementOut(BaseModel):
    as_of: date
    total_g: str
    vault_g: str
    karigars_g: str
    refiner_g: str
    consistent: bool
    basis: str
    holders: list[HolderOut]


class StockEntryOut(BaseModel):
    id: int
    entry_date: date
    kind: str
    label: str
    fine_weight_g: str
    note: str | None
    by: str


class MoveOut(BaseModel):
    entry: StockEntryOut
    statement: StatementOut


def _holders(db: Session, as_of: date):
    return db.execute(
        select(
            Karigar.id,
            Karigar.name,
            func.coalesce(func.sum(LedgerEntry.balance_delta_mg), 0),
        )
        .select_from(Karigar)
        .join(LedgerEntry, LedgerEntry.karigar_id == Karigar.id)
        .where(LedgerEntry.entry_date <= as_of)
        .group_by(Karigar.id, Karigar.name)
        .order_by(Karigar.name)
    ).all()


def _compute(db: Session, as_of: date) -> tuple[StockStatement, list]:
    sums = dict(
        db.execute(
            select(StockEntry.kind, func.coalesce(func.sum(StockEntry.fine_mg), 0))
            .where(StockEntry.entry_date <= as_of)
            .group_by(StockEntry.kind)
        ).all()
    )
    bought = db.scalar(
        select(func.coalesce(func.sum(OldGoldPurchase.fine_mg), 0)).where(
            OldGoldPurchase.entry_date <= as_of
        )
    )
    # A void counts from the day it was made, so earlier statements don't change.
    voided = db.scalar(
        select(func.coalesce(func.sum(OldGoldPurchase.fine_mg), 0))
        .select_from(OldGoldPurchase)
        .join(OldGoldVoid, OldGoldVoid.purchase_id == OldGoldPurchase.id)
        .where(OldGoldVoid.voided_on <= as_of)
    )
    holders = _holders(db, as_of)
    statement = compute_statement(
        total_mg=sums.get(STOCK_OPENING, 0) + bought - voided,
        sent_mg=sums.get(STOCK_TO_REFINER, 0),
        received_mg=sums.get(STOCK_FROM_REFINER, 0),
        karigars_mg=sum(balance for _id, _name, balance in holders),
    )
    return statement, holders


def _statement_out(db: Session, as_of: date) -> StatementOut:
    statement, holders = _compute(db, as_of)
    return StatementOut(
        as_of=as_of,
        total_g=format_weight_g(statement.total_mg),
        vault_g=format_weight_g(statement.vault_mg),
        karigars_g=format_weight_g(statement.karigars_mg),
        refiner_g=format_weight_g(statement.refiner_mg),
        consistent=statement.consistent,
        basis=BASIS,
        holders=[
            HolderOut(karigar_id=i, karigar=name, balance_g=format_weight_g(balance))
            for i, name, balance in holders
            if balance != 0
        ],
    )


def _day(as_of: date | None) -> date:
    today = today_ist()
    day = as_of or today
    if day > today:
        raise HTTPException(status_code=422, detail="The date can't be in the future.")
    return day


@router.get("/statement", response_model=StatementOut)
def statement(
    as_of: date | None = None,
    db: Session = Depends(get_session),
    _user: User = Depends(require_roles(ROLE_FINANCE_HEAD)),
):
    return _statement_out(db, _day(as_of))


@router.get("/statement.csv")
def statement_csv(
    as_of: date | None = None,
    db: Session = Depends(get_session),
    _user: User = Depends(require_roles(ROLE_FINANCE_HEAD)),
):
    """A plain CSV, standing in for the Tally import format, which isn't specified."""
    day = _day(as_of)
    data = _statement_out(db, day)
    stamp = day.isoformat()
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(["Date", "Particulars", "Fine gold (g)"])
    writer.writerow([stamp, "Vault", data.vault_g])
    for holder in data.holders:
        writer.writerow([stamp, f"With karigar: {holder.karigar}", holder.balance_g])
    writer.writerow([stamp, "With karigars (total)", data.karigars_g])
    writer.writerow([stamp, "At refiner", data.refiner_g])
    writer.writerow([stamp, "Total stock", data.total_g])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="aurum-stock-{stamp}.csv"'},
    )


@router.get("/entries", response_model=list[StockEntryOut])
def entries(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_session),
    _user: User = Depends(require_roles(ROLE_FINANCE_HEAD)),
):
    rows = db.execute(
        select(StockEntry, User.full_name)
        .join(User, User.id == StockEntry.created_by)
        .order_by(StockEntry.entry_date.desc(), StockEntry.id.desc())
        .limit(limit)
    ).all()
    return [_entry_out(entry, name) for entry, name in rows]


def _entry_out(entry: StockEntry, by: str) -> StockEntryOut:
    return StockEntryOut(
        id=entry.id,
        entry_date=entry.entry_date,
        kind=entry.kind,
        label=LABELS[entry.kind],
        fine_weight_g=format_weight_g(entry.fine_mg),
        note=entry.note,
        by=by,
    )


@router.post("/refiner", response_model=MoveOut, status_code=201)
def move_refiner(
    body: RefinerIn,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(ROLE_FINANCE_HEAD)),
):
    try:
        mg = parse_weight_g(body.fine_weight)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail=WEIGHT_HELP)
    if mg <= 0:
        raise HTTPException(status_code=422, detail="The weight must be above 0.")
    if mg > MAX_REFINER_MG:
        raise HTTPException(
            status_code=422,
            detail=f"A single movement can't be more than {format_weight_g(MAX_REFINER_MG)} g.",
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

    current, _holders_now = _compute(db, today)
    sending = body.direction == "SEND"
    if sending and mg > current.vault_mg:
        raise HTTPException(
            status_code=422,
            detail=f"Only {format_weight_g(max(current.vault_mg, 0))} g is in the vault.",
        )
    if not sending and mg > current.refiner_mg:
        raise HTTPException(
            status_code=422,
            detail=f"Only {format_weight_g(max(current.refiner_mg, 0))} g is at the refiner.",
        )

    entry = StockEntry(
        entry_date=entry_date,
        kind=STOCK_TO_REFINER if sending else STOCK_FROM_REFINER,
        fine_mg=mg,
        note=body.note,
        created_by=user.id,
    )
    db.add(entry)
    db.flush()
    record(
        db,
        user.id,
        "stock.sent_to_refiner" if sending else "stock.received_from_refiner",
        "stock_entry",
        entry.id,
        f"{format_weight_g(mg)} g fine",
    )
    db.commit()
    return MoveOut(entry=_entry_out(entry, user.full_name), statement=_statement_out(db, today))