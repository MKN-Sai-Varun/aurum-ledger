from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import require_roles
from app.domain.alerts_math import (
    DRIFT_MIN_JOBS,
    DRIFT_THRESHOLD_H,
    JobLoss,
    detect_drift,
)
from app.domain.gold_math import format_pct, format_weight_g
from app.domain.job_math import needs_review
from app.models import ROLE_FINANCE_HEAD, Job, Karigar, User
from app.routers.jobs import _summaries

router = APIRouter(prefix="/api", tags=["alerts"])

RULES = [
    "A closed job is listed when more fine gold is still outstanding than the agreed wastage allows.",
    (
        f"A trend is listed when a karigar has at least {DRIFT_MIN_JOBS} closed jobs, and the latest "
        f"job's difference beyond the allowance is above zero and at least "
        f"{format_pct(DRIFT_THRESHOLD_H)} percentage points higher than the average of their earlier jobs."
    ),
    "These are prompts to look closer, not conclusions.",
]


class Figure(BaseModel):
    label: str
    value: str


class AlertOut(BaseModel):
    id: str
    kind: str
    karigar_id: int
    karigar: str
    job_no: str | None
    title: str
    message: str
    figures: list[Figure]


class AlertsOut(BaseModel):
    drift_count: int
    review_count: int
    rules: list[str]
    alerts: list[AlertOut]


def _signed_pct(hundredths: int) -> str:
    sign = "-" if hundredths < 0 else ""
    value = abs(hundredths)
    return f"{sign}{value // 100}.{value % 100:02d}"


@router.get("/alerts", response_model=AlertsOut)
def list_alerts(
    db: Session = Depends(get_session),
    _user: User = Depends(require_roles(ROLE_FINANCE_HEAD)),
):
    closed = list(db.scalars(select(Job).where(Job.status == "CLOSED")))
    summaries = _summaries(db, closed)
    names = {k.id: k.name for k in db.scalars(select(Karigar))}

    history: dict[int, list[JobLoss]] = {}
    flagged = []
    for job in closed:
        summary = summaries.get(job.id)
        if summary is None:
            continue
        closed_on = job.closed_on or job.opened_on
        history.setdefault(job.karigar_id, []).append(
            JobLoss(job.job_no, closed_on, summary.issued_mg, summary.unexplained_mg)
        )
        if needs_review(job.status, summary.unexplained_mg):
            flagged.append((closed_on, job, summary))

    drift_alerts: list[AlertOut] = []
    for karigar_id in sorted(history, key=lambda k: names.get(k, "")):
        drift = detect_drift(history[karigar_id])
        if drift is None:
            continue
        name = names[karigar_id]
        drift_alerts.append(
            AlertOut(
                id=f"drift:{karigar_id}",
                kind="KARIGAR_DRIFT",
                karigar_id=karigar_id,
                karigar=name,
                job_no=drift.latest_job_no,
                title="Trend to review",
                message=(
                    f"On {drift.latest_job_no} the difference beyond the agreed wastage was "
                    f"{_signed_pct(drift.latest_rate_h)} % of the fine gold issued, against an average "
                    f"of {_signed_pct(drift.baseline_rate_h)} % on {drift.earlier_jobs} earlier jobs. "
                    "The trend may be worth a conversation."
                ),
                figures=[
                    Figure(label="Latest job", value=drift.latest_job_no),
                    Figure(label="Latest difference", value=f"{_signed_pct(drift.latest_rate_h)} %"),
                    Figure(label="Earlier average", value=f"{_signed_pct(drift.baseline_rate_h)} %"),
                    Figure(label="Earlier jobs", value=str(drift.earlier_jobs)),
                ],
            )
        )

    flagged.sort(key=lambda item: (item[0], item[1].job_no), reverse=True)
    review_alerts = [
        AlertOut(
            id=f"job:{job.job_no}",
            kind="JOB_REVIEW",
            karigar_id=job.karigar_id,
            karigar=names[job.karigar_id],
            job_no=job.job_no,
            title="Job to review",
            message=(
                f"{job.job_no} closed with {format_weight_g(summary.unexplained_mg)} g more fine gold "
                f"outstanding than the agreed wastage allows ({format_weight_g(summary.allowed_mg)} g "
                f"at {format_pct(summary.wastage_hundredths)} %). Worth a look at the receipts."
            ),
            figures=[
                Figure(label="Outstanding", value=f"{format_weight_g(summary.outstanding_mg)} g"),
                Figure(label="Allowed wastage", value=f"{format_weight_g(summary.allowed_mg)} g"),
                Figure(
                    label="Beyond the allowance",
                    value=f"{format_weight_g(summary.unexplained_mg)} g",
                ),
            ],
        )
        for _closed_on, job, summary in flagged
    ]

    return AlertsOut(
        drift_count=len(drift_alerts),
        review_count=len(review_alerts),
        rules=RULES,
        alerts=drift_alerts + review_alerts,
    )