import hashlib
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit import record
from app.db import get_session, settings
from app.deps import require_roles
from app.models import ROLE_ISSUE_CLERK, Reading, User
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


def get_providers() -> list:
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