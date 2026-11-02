"""Helper for writing audit log rows. The caller commits."""
from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    user_id: int | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    detail: str | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            detail=detail[:500] if detail else None,
        )
    )