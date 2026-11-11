"""Recheck asynchronous authority at worker boundaries, after queue admission."""

from sqlalchemy import select

from app.core.errors import fail
from app.modules.workspaces.models import WorkspaceMember


def assert_authorized(db, run):
    role = db.scalar(select(WorkspaceMember.role).where(WorkspaceMember.workspace_id == run.workspace_id, WorkspaceMember.user_id == run.requested_by))
    if role not in {"owner", "admin", "editor"}:
        fail(403, "RUN_AUTHORIZATION_REVOKED", "The run requester no longer has permission to execute in this workspace.")
    if run.deployment_id:
        from app.modules.deployments.models import Deployment
        deployment = db.scalar(select(Deployment).where(Deployment.id == run.deployment_id, Deployment.workspace_id == run.workspace_id))
        if not deployment or deployment.state != "active" or deployment.created_by != run.requested_by or role not in {"owner", "admin"}:
            fail(403, "RUN_AUTHORIZATION_REVOKED", "This deployment or its creator no longer has execution permission.")
