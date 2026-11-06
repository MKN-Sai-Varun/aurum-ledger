"""The karigar's own read-only view. Everything is filtered by the signed-in login."""
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import require_roles
from app.domain.gold_math import format_pct, format_weight_g
from app.ledger import karigar_balance_mg
from app.models import ROLE_KARIGAR, Job, Karigar, LedgerEntry, User
from app.routers.corrections import _signed_g
from app.routers.jobs import JobOut, _job_outs

router = APIRouter(prefix="/api/me", tags=["me"])

MAX_ENTRIES = 50
MAX_JOBS = 30


class MyEntry(BaseModel):
    txn_no: str
    entry_date: date
    kind: str
    job_no: str
    category: str
    gross_weight_g: str
    purity_pct: str
    fine_weight_g: str
    change_g: str
    huid: str | None


class MySummary(BaseModel):
    karigar: str
    balance_g: str
    open_jobs: int
    jobs: list[JobOut]
    entries: list[MyEntry]
    truncated: bool


@router.get("/summary", response_model=MySummary)
def my_summary(
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(ROLE_KARIGAR)),
):
    # The karigar comes from the login row, never from the request.
    karigar = db.get(Karigar, user.karigar_id)

    jobs = list(
        db.scalars(
            select(Job)
            .where(Job.karigar_id == karigar.id)
            .order_by(Job.opened_on.desc(), Job.id.desc())
            .limit(MAX_JOBS)
        )
    )
    # Review flags are for the finance head only, so they are never requested here.
    job_outs = _job_outs(db, jobs, show_review=False)
    by_id = {job.id: out for job, out in zip(jobs, job_outs)}

    rows = list(
        db.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.karigar_id == karigar.id)
            .order_by(LedgerEntry.entry_date.desc(), LedgerEntry.id.desc())
            .limit(MAX_ENTRIES + 1)
        )
    )
    missing = {e.job_id for e in rows if e.job_id not in by_id}
    if missing:
        extra = list(db.scalars(select(Job).where(Job.id.in_(missing))))
        for job, out in zip(extra, _job_outs(db, extra, show_review=False)):
            by_id[job.id] = out

    entries = [
        MyEntry(
            txn_no=e.txn_no,
            entry_date=e.entry_date,
            kind=e.kind,
            job_no=by_id[e.job_id].job_no,
            category=by_id[e.job_id].category,
            gross_weight_g=format_weight_g(e.gross_mg),
            purity_pct=format_pct(e.purity_hundredths),
            fine_weight_g=format_weight_g(e.fine_mg),
            change_g=_signed_g(e.balance_delta_mg),
            huid=e.huid,
        )
        for e in rows[:MAX_ENTRIES]
    ]
    return MySummary(
        karigar=karigar.name,
        balance_g=format_weight_g(karigar_balance_mg(db, karigar.id)),
        open_jobs=sum(1 for out in job_outs if out.status == "OPEN"),
        jobs=job_outs,
        entries=entries,
        truncated=len(rows) > MAX_ENTRIES,
    )