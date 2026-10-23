import uuid

from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent


def record(
    db: Session,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    target_id: uuid.UUID,
    details: dict,
) -> None:
    """Participate in caller's transaction. Details contain IDs/counts, never config payloads."""
    db.add(
        AuditEvent(
            workspace_id=workspace_id,
            actor_id=actor_id,
            action=action,
            target_id=target_id,
            details=details,
        )
    )
