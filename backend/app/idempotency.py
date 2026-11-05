"""Safe retries for saves.

A save may carry an Idempotency-Key. The key is stored together with the entry
it created, in the same transaction. A second request with the same key returns
that entry and creates nothing, even if the data would no longer validate (for
example a receipt that already used up the outstanding gold).
"""
import hashlib
import re
from dataclasses import dataclass
from typing import Callable

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IdempotencyKey

KEY_RE = re.compile(r"[A-Za-z0-9_-]{16,64}")


class Replay(Exception):
    """Raised to answer a repeated save with the original result."""

    def __init__(self, payload):
        super().__init__("replay")
        self.payload = payload


@dataclass
class Guard:
    user_id: int
    key: str | None
    scope: str
    digest: str
    rebuild: Callable[[str], object]

    def raise_if_stored(self, db: Session) -> None:
        if self.key is None:
            return
        row = db.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == self.user_id,
                IdempotencyKey.key == self.key,
            )
        )
        if row is None:
            return
        if row.scope != self.scope or row.request_hash != self.digest:
            raise HTTPException(
                status_code=422,
                detail="This key was already used for a different request.",
            )
        raise Replay(jsonable_encoder(self.rebuild(row.ref)))

    def remember(self, db: Session, ref: str) -> None:
        """Store the key with the new entry. Call just before committing."""
        if self.key is None:
            return
        db.add(
            IdempotencyKey(
                user_id=self.user_id,
                key=self.key,
                scope=self.scope,
                request_hash=self.digest,
                ref=ref,
            )
        )


def begin(
    db: Session,
    user_id: int,
    key: str | None,
    scope: str,
    body_json: str,
    rebuild: Callable[[str], object],
) -> Guard:
    """Check the key and answer a repeat straight away. Call first in an endpoint."""
    if key is not None and not KEY_RE.fullmatch(key):
        raise HTTPException(
            status_code=422,
            detail="The idempotency key must be 16 to 64 letters, digits, - or _.",
        )
    guard = Guard(
        user_id=user_id,
        key=key,
        scope=scope,
        digest=hashlib.sha256(body_json.encode("utf-8")).hexdigest(),
        rebuild=rebuild,
    )
    guard.raise_if_stored(db)
    return guard