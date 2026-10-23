"""Remove only the account/resources created by scripts/smoke.mjs."""
import json
import re
import sys
import uuid

from sqlalchemy import delete, select

from app.main import app
from app.modules.agents.models import Agent
from app.modules.identity.models import AccountToken, EmailDelivery, User, UserSession
from app.modules.workflows.models import Workflow
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
    for model in [Agent, Workflow, WorkspaceMember]:
        db.execute(delete(model).where(model.workspace_id == workspace_id))
    db.execute(delete(UserSession).where(UserSession.user_id == user_id))
    db.execute(delete(AccountToken).where(AccountToken.user_id == user_id))
    db.execute(delete(EmailDelivery).where(EmailDelivery.user_id == user_id))
    db.delete(workspace)
    db.flush()
    db.delete(user)
    db.commit()
print("Only the temporary smoke-check account and its workspace were removed.")
