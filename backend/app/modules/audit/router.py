"""Bounded, workspace-scoped activity pages. Configuration and secrets are never exported."""

import base64
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import fail
from app.modules.audit.models import AuditEvent
from app.modules.workspaces.service import authorize

router = APIRouter(prefix="/workspaces/{workspace_id}/activity", tags=["activity"])


class ActivityRead(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID
    action: str
    target_id: uuid.UUID
    details: dict
    created_at: datetime


class ActivityPage(BaseModel):
    items: list[ActivityRead]
    next_cursor: str | None


@router.get("", response_model=ActivityPage)
def listing(
    workspace_id: uuid.UUID,
    request: Request,
    cursor: str | None = Query(default=None, max_length=256),
    action: str | None = Query(default=None, max_length=100, pattern=r"^[a-z][a-z0-9_.]*$"),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _, member = authorize(request, db, workspace_id)
    if member.role not in {"owner", "admin"}:
        fail(403, "FORBIDDEN", "An owner or admin can read and export workspace activity.")
    query = select(AuditEvent).where(AuditEvent.workspace_id == workspace_id)
    if action:
        query = query.where(AuditEvent.action == action)
    if cursor:
        try:
            raw = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
            if not isinstance(raw, list) or len(raw) != 2:
                raise ValueError
            created, identity = datetime.fromisoformat(raw[0]), uuid.UUID(raw[1])
            if created.tzinfo is None:
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            fail(422, "CURSOR_INVALID", "This activity page cursor is invalid. Refresh the list.")
        query = query.where(
            tuple_(AuditEvent.created_at, AuditEvent.id) < tuple_(created, identity)
        )
    rows = db.scalars(
        query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit + 1)
    ).all()
    page, after = rows[:limit], None
    if len(rows) > limit:
        after = base64.urlsafe_b64encode(
            json.dumps([page[-1].created_at.isoformat(), str(page[-1].id)]).encode()
        ).decode()
    return {
        "items": [
            {
                key: getattr(row, key)
                for key in ("id", "actor_id", "action", "target_id", "details", "created_at")
            }
            for row in page
        ],
        "next_cursor": after,
    }
