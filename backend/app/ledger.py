"""Ledger helpers shared by routers."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from app.models import LedgerEntry

# India has no daylight saving, so a fixed offset is exact.
IST = timezone(timedelta(hours=5, minutes=30))


def today_ist() -> date:
    return datetime.now(IST).date()


def karigar_balance_mg(db: Session, karigar_id: int, as_of: date | None = None) -> int:
    """Fine gold a karigar holds, in milligrams, as of the end of a day."""
    query = select(func.coalesce(func.sum(LedgerEntry.balance_delta_mg), 0)).where(
        LedgerEntry.karigar_id == karigar_id
    )
    if as_of is not None:
        query = query.where(LedgerEntry.entry_date <= as_of)
    return db.scalar(query)


def next_number(db: Session, column, prefix: str, first: int) -> str:
    """Next number in a sequence such as JOB-1047, one above the highest so far."""
    highest = db.scalar(
        select(func.max(cast(func.substr(column, len(prefix) + 1), Integer)))
    )
    return f"{prefix}{(highest or first - 1) + 1}"