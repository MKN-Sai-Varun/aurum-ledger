from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import record
from app.db import get_session
from app.deps import require_roles
from app.domain.aging import BUCKETS, age_days, bucket_key
from app.domain.gold_math import format_weight_g
from app.ledger import today_ist
from app.models import ROLE_FINANCE_HEAD, Job, JobFollowUp, LedgerEntry, User
from app.routers.jobs import _get_job, _job_outs, _summaries

router = APIRouter(prefix="/api", tags=["aging"])


class FollowUpIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(min_length=3, max_length=200)

    @field_validator("note", mode="before")
    @classmethod
    def tidy_note(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value


class FollowUpOut(BaseModel):
    job_no: str
    followed_up_on: date
    note: str
    by: str


class AgingJob(BaseModel):
    job_no: str
    karigar_id: int
    karigar: str
    category: str
    opened_on: date
    age_days: int
    issued_fine_g: str
    outstanding_g: str
    last_activity: date | None
    days_since_activity: int | None
    followups: int
    last_followup_on: date | None
    last_followup_note: str | None
    last_followup_by: str | None


class Bucket(BaseModel):
    key: str
    label: str
    count: int
    outstanding_g: str
    jobs: list[AgingJob]


class AgingOut(BaseModel):
    as_of: date
    total_open: int
    total_outstanding_g: str
    buckets: list[Bucket]


def _as_date(value):
    return date.fromisoformat(value) if isinstance(value, str) else value


@router.get("/job-aging", response_model=AgingOut)
def job_aging(
    db: Session = Depends(get_session),
    _user: User = Depends(require_roles(ROLE_FINANCE_HEAD)),
):
    today = today_ist()
    jobs = list(db.scalars(select(Job).where(Job.status == "OPEN")))
    ids = [job.id for job in jobs] or [0]

    summaries = _summaries(db, jobs)
    shown = {out.job_no: out for out in _job_outs(db, jobs, show_review=False)}

    last_activity = {
        job_id: _as_date(day)
        for job_id, day in db.execute(
            select(LedgerEntry.job_id, func.max(LedgerEntry.entry_date))
            .where(LedgerEntry.job_id.in_(ids))
            .group_by(LedgerEntry.job_id)
        ).all()
    }

    followups: dict[int, list] = {}
    rows = db.execute(
        select(JobFollowUp, User.full_name)
        .join(User, User.id == JobFollowUp.created_by)
        .where(JobFollowUp.job_id.in_(ids))
        .order_by(JobFollowUp.id.desc())
    ).all()
    for row, name in rows:
        followups.setdefault(row.job_id, []).append((row, name))

    grouped: dict[str, list] = {key: [] for key, _l, _lo, _hi in BUCKETS}
    totals_mg: dict[str, int] = {key: 0 for key, _l, _lo, _hi in BUCKETS}

    for job in jobs:
        out = shown[job.job_no]
        age = age_days(job.opened_on, today)
        key = bucket_key(age)
        summary = summaries.get(job.id)
        totals_mg[key] += summary.outstanding_mg if summary else 0

        last = last_activity.get(job.id)
        notes = followups.get(job.id, [])
        latest, latest_by = notes[0] if notes else (None, None)
        grouped[key].append(
            (
                age,
                job.job_no,
                AgingJob(
                    job_no=job.job_no,
                    karigar_id=job.karigar_id,
                    karigar=out.karigar,
                    category=out.category,
                    opened_on=job.opened_on,
                    age_days=age,
                    issued_fine_g=out.issued_fine_g,
                    outstanding_g=out.outstanding_g,
                    last_activity=last,
                    days_since_activity=max(0, (today - last).days) if last else None,
                    followups=len(notes),
                    last_followup_on=latest.followed_up_on if latest else None,
                    last_followup_note=latest.note if latest else None,
                    last_followup_by=latest_by,
                ),
            )
        )

    buckets = []
    for key, label, _low, _high in BUCKETS:
        ordered = sorted(grouped[key], key=lambda item: (-item[0], item[1]))
        buckets.append(
            Bucket(
                key=key,
                label=label,
                count=len(ordered),
                outstanding_g=format_weight_g(totals_mg[key]),
                jobs=[item[2] for item in ordered],
            )
        )
    return AgingOut(
        as_of=today,
        total_open=len(jobs),
        total_outstanding_g=format_weight_g(sum(totals_mg.values())),
        buckets=buckets,
    )


@router.post(
    "/job-aging/{job_no}/follow-ups", response_model=FollowUpOut, status_code=201
)
def add_follow_up(
    job_no: str,
    body: FollowUpIn,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(ROLE_FINANCE_HEAD)),
):
    job = _get_job(db, job_no)
    if job.status != "OPEN":
        raise HTTPException(status_code=409, detail="This job is closed.")
    day = today_ist()
    job_id, number, user_id, user_name = job.id, job.job_no, user.id, user.full_name
    db.add(
        JobFollowUp(job_id=job_id, note=body.note, followed_up_on=day, created_by=user_id)
    )
    db.flush()
    record(db, user_id, "job.followed_up", "job", job_id, f"{number}: {body.note}")
    db.commit()
    return FollowUpOut(job_no=number, followed_up_on=day, note=body.note, by=user_name)