import hashlib
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from datetime import datetime

from app.audit import record
from app.readers.base import Reader
from app.db import get_session, settings
from app.deps import require_roles
from app.models import (
    READING_ACCEPTED,
    READING_CORRECTED,
    READING_PENDING,
    ROLE_FINANCE_HEAD,
    ROLE_ISSUE_CLERK,
    Reading,
    User,
)
from app.ratelimit import LoginLimiter
from app.readers.gemini import GeminiReader
from app.readers.image import MAX_BYTES, prepare_image
from app.readers.service import read_value
from app.readers.tesseract import TesseractReader

router = APIRouter(prefix="/api", tags=["readings"])

# Reuses the lockout counter as a plain usage counter: every request counts once.
usage_limiter = LoginLimiter(max_failures=30, window_seconds=600)

SOURCE_LABELS = {
    "GEMINI": "AI reader",
    "TESSERACT": "Local reader",
    "NONE": "Not read",
}


def get_providers() -> list[Reader]:
    """Readers in the order they are tried. One that isn't set up is skipped."""
    return [
        GeminiReader(settings.gemini_api_key, settings.gemini_model),
        TesseractReader(),
    ]


class ReadingOut(BaseModel):
    id: int
    target: str
    source: str
    source_label: str
    value: str | None
    readable: bool
    notes: list[str]


@router.post("/readings", response_model=ReadingOut, status_code=201)
def create_reading(
    target: Literal["WEIGHT", "PURITY"] = Form(),
    image: UploadFile = File(),
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(ROLE_ISSUE_CLERK)),
    providers: list = Depends(get_providers),
):
    key = str(user.id)
    if usage_limiter.is_blocked(key):
        raise HTTPException(
            status_code=429,
            detail="Too many photo readings. Wait a few minutes, or type the value.",
        )
    usage_limiter.record_failure(key)

    raw = image.file.read(MAX_BYTES + 1)
    try:
        jpeg = prepare_image(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    outcome = read_value(providers, target, jpeg)

    reading = Reading(
        user_id=user.id,
        target=target,
        source=outcome.source,
        value_text=outcome.value,
        image_sha256=hashlib.sha256(raw).hexdigest(),
    )
    db.add(reading)
    db.flush()
    record(db, user.id, "reading.created", "reading", reading.id,
           f"{target} via {outcome.source}")
    db.commit()

    return ReadingOut(
        id=reading.id,
        target=target,
        source=outcome.source,
        source_label=SOURCE_LABELS[outcome.source],
        value=outcome.value,
        readable=outcome.value is not None,
        notes=outcome.notes,
    )

class CorrectionOut(BaseModel):
    txn_no: str | None
    target: str
    read_value: str | None
    entered_value: str | None
    reason: str | None
    by: str
    at: datetime | None


class SummaryOut(BaseModel):
    total: int
    accepted: int
    corrected: int
    unused: int
    unreadable: int
    correction_rate_pct: str | None
    by_source: dict[str, int]
    recent_corrections: list[CorrectionOut]


@router.get("/readings/summary", response_model=SummaryOut)
def readings_summary(
    db: Session = Depends(get_session),
    _user: User = Depends(require_roles(ROLE_FINANCE_HEAD)),
):
    by_status = dict(db.execute(select(Reading.status, func.count()).group_by(Reading.status)).all())
    by_source = dict(db.execute(select(Reading.source, func.count()).group_by(Reading.source)).all())
    unreadable = db.scalar(
        select(func.count()).select_from(Reading).where(Reading.value_text.is_(None))
    )
    accepted = by_status.get(READING_ACCEPTED, 0)
    corrected = by_status.get(READING_CORRECTED, 0)
    resolved = accepted + corrected

    rate = None
    if resolved:
        tenths = (2 * corrected * 1000 + resolved) // (2 * resolved)
        rate = f"{tenths // 10}.{tenths % 10}"

    rows = db.execute(
        select(Reading, User.full_name)
        .join(User, User.id == Reading.user_id)
        .where(Reading.status == READING_CORRECTED)
        .order_by(Reading.resolved_at.desc(), Reading.id.desc())
        .limit(10)
    ).all()

    return SummaryOut(
        total=sum(by_status.values()),
        accepted=accepted,
        corrected=corrected,
        unused=by_status.get(READING_PENDING, 0),
        unreadable=unreadable,
        correction_rate_pct=rate,
        by_source=by_source,
        recent_corrections=[
            CorrectionOut(
                txn_no=reading.txn_no,
                target=reading.target,
                read_value=reading.value_text,
                entered_value=reading.confirmed_text,
                reason=reading.override_reason,
                by=name,
                at=reading.resolved_at,
            )
            for reading, name in rows
        ],
    )