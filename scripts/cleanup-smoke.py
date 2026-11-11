"""Remove only the account/resources created by scripts/smoke.mjs."""
import json
import re
import secrets
import sys
import uuid

from sqlalchemy import delete, select

from app.main import app
from app.modules.agents.evaluations import EvaluationSuite
from app.modules.agents.models import Agent, AgentVersion
from app.modules.audit.models import AuditEvent
from app.modules.identity.models import AccountToken, EmailDelivery, User, UserSession
from app.modules.identity.service import hasher
from app.modules.workflows.models import Workflow, WorkflowVersion
from app.modules.workspaces.models import Workspace, WorkspaceMember

resource = json.load(sys.stdin)
if not re.fullmatch(r"smoke-[a-f0-9]{16}@example\.com", resource["email"]):
    raise ValueError("Not a smoke-check identity")
user_id, workspace_id = uuid.UUID(resource["user_id"]), uuid.UUID(resource["workspace_id"])
with app.state.sessions() as db:
    user = db.scalar(select(User).where(User.id == user_id, User.email == resource["email"]))
    workspace = db.scalar(select(Workspace).where(Workspace.id == workspace_id, Workspace.created_by == user_id, Workspace.name == "Temporary smoke check"))
    if not user or not workspace:
        raise ValueError("Temporary resources do not match; no cleanup performed")
    has_audit = db.scalar(select(AuditEvent.id).where(AuditEvent.workspace_id == workspace_id).limit(1))
    for model in [EvaluationSuite, Agent, Workflow] + ([] if has_audit else [WorkspaceMember]):
        query = delete(model).where(model.workspace_id == workspace_id)
        if model is Agent:
            query = query.where(~select(AgentVersion.id).where(AgentVersion.agent_id == Agent.id).exists())
        elif model is Workflow:
            query = query.where(~select(WorkflowVersion.id).where(WorkflowVersion.workflow_id == Workflow.id).exists())
        db.execute(query)
    db.execute(delete(UserSession).where(UserSession.user_id == user_id))
    db.execute(delete(AccountToken).where(AccountToken.user_id == user_id))
    db.execute(delete(EmailDelivery).where(EmailDelivery.user_id == user_id))
    if has_audit and not db.scalar(select(WorkspaceMember.id).where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)):
        db.add(WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="owner"))
    if not has_audit:
        db.delete(workspace)
        db.flush()
        db.delete(user)
    else:
        # Published fixture history remains auditable, but its discarded test
        # password and sessions must no longer authorize access.
        user.password_hash = hasher.hash(secrets.token_urlsafe(48))
    db.commit()
print("Temporary smoke artifacts and sessions removed; immutable audit identities retained when required.")
