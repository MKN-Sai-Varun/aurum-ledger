"""Server-side confirmation of photo readings.

A request may carry the id of a photo reading for the weight and for the
purity. The typed value is compared with what the reading found. A mismatch
blocks the save unless the clerk gives a written reason, in which case the
reading is recorded as corrected. Readings are resolved in the same
transaction as the ledger entry.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.audit import record
from app.models import (
    READING_ACCEPTED,
    READING_CORRECTED,
    READING_PENDING,
    Reading,
    User,
)

MAX_AGE = timedelta(minutes=30)
MIN_REASON = 5


class ReadingFields(BaseModel):
    """Optional fields shared by issue and receipt requests."""

    weight_reading_id: StrictInt | None = Field(default=None, gt=0)
    weight_override_reason: str | None = Field(default=None, max_length=150)
    purity_reading_id: StrictInt | None = Field(default=None, gt=0)
    purity_override_reason: str | None = Field(default=None, max_length=150)

    @field_validator("weight_override_reason", "purity_override_reason", mode="before")
    @classmethod
    def tidy_reason(cls, value):
        if isinstance(value, str):
            return " ".join(value.split()) or None
        return value

    @model_validator(mode="after")
    def reason_needs_a_reading(self):
        if self.weight_override_reason and self.weight_reading_id is None:
            raise ValueError("A weight reason needs a weight photo reading.")
        if self.purity_override_reason and self.purity_reading_id is None:
            raise ValueError("A purity reason needs a purity photo reading.")
        return self


@dataclass(frozen=True)
class Confirmation:
    reading_id: int
    target: str
    status: str
    typed: str
    read: str
    override_reason: str | None


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _check_one(
    db: Session,
    user: User,
    reading_id: int,
    target: str,
    label: str,
    typed: str,
    reason: str | None,
) -> Confirmation:
    reading = db.get(Reading, reading_id)
    if reading is None or reading.user_id != user.id or reading.target != target:
        raise HTTPException(
            status_code=422,
            detail=f"The {label} photo reading wasn't found. Take the photo again.",
        )
    if reading.status != READING_PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"The {label} photo reading has already been used. Take the photo again.",
        )
    if datetime.now(timezone.utc) - _aware(reading.created_at) > MAX_AGE:
        raise HTTPException(
            status_code=422,
            detail=f"The {label} photo reading is too old. Take the photo again.",
        )
    if reading.value_text is None:
        raise HTTPException(
            status_code=422,
            detail=f"The {label} photo reading has no value to confirm. Type the value without it.",
        )

    if typed == reading.value_text:
        return Confirmation(reading.id, target, READING_ACCEPTED, typed, reading.value_text, None)

    if not reason:
        raise HTTPException(
            status_code=409,
            detail=(
                f"The {label} you entered ({typed}) doesn't match the photo reading "
                f"({reading.value_text}). Use the reading, or give a reason to override it."
            ),
        )
    if len(reason) < MIN_REASON:
        raise HTTPException(
            status_code=422,
            detail=f"Give a reason of at least {MIN_REASON} characters.",
        )
    return Confirmation(reading.id, target, READING_CORRECTED, typed, reading.value_text, reason)


def check_readings(
    db: Session, user: User, body: ReadingFields, weight: str, purity: str
) -> list[Confirmation]:
    """Compare the typed weight and purity with any attached readings.

    Raises HTTPException when a reading is unusable or a mismatch is unexplained.
    Nothing is written here.
    """
    found: list[Confirmation] = []
    if body.weight_reading_id is not None:
        found.append(
            _check_one(db, user, body.weight_reading_id, "WEIGHT", "weight",
                       weight, body.weight_override_reason)
        )
    if body.purity_reading_id is not None:
        found.append(
            _check_one(db, user, body.purity_reading_id, "PURITY", "purity",
                       purity, body.purity_override_reason)
        )
    return found


def apply_readings(
    db: Session, user_id: int, confirmations: list[Confirmation], txn_no: str
) -> None:
    """Mark the readings used. Call just before committing the ledger entry."""
    now = datetime.now(timezone.utc)
    for item in confirmations:
        result = db.execute(
            update(Reading)
            .where(Reading.id == item.reading_id, Reading.status == READING_PENDING)
            .values(
                status=item.status,
                confirmed_text=item.typed,
                override_reason=item.override_reason,
                txn_no=txn_no,
                resolved_at=now,
            )
        )
        if result.rowcount != 1:
            raise HTTPException(
                status_code=409,
                detail="A photo reading was already used. Take the photo again.",
            )
        if item.status == READING_ACCEPTED:
            record(db, user_id, "reading.accepted", "reading", item.reading_id,
                   f"{txn_no} {item.target} {item.typed}")
        else:
            record(db, user_id, "reading.corrected", "reading", item.reading_id,
                   f"{txn_no} {item.target}: photo {item.read}, entered {item.typed}: "
                   f"{item.override_reason}")