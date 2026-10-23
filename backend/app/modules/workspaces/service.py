import uuid

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import fail
from app.modules.identity.service import current_session
from app.modules.workspaces.models import Workspace, WorkspaceMember


def authorize(
    request: Request, db: Session, workspace_id: uuid.UUID, write: bool = False
) -> tuple[Workspace, WorkspaceMember]:
    user, _ = current_session(request, db)
    member = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user.id
        )
    )
    if not member:
        fail(404, "NOT_FOUND", "Workspace not found.")
    if write and member.role == "viewer":
        fail(403, "FORBIDDEN", "An editor role is required for this action.")
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        fail(404, "NOT_FOUND", "Workspace not found.")
    return workspace, member
