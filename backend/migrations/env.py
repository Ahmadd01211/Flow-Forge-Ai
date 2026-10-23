from alembic import context
from sqlalchemy import create_engine

from app.core.config import Settings
from app.core.db import Base
from app.modules.agents.models import Agent, AgentVersion  # noqa: F401
from app.modules.audit.models import AuditEvent  # noqa: F401
from app.modules.deployments.models import Deployment  # noqa: F401
from app.modules.executions.models import AgentRun, RunEvent  # noqa: F401
from app.modules.identity.models import AccountToken, EmailDelivery, User, UserSession  # noqa: F401
from app.modules.integrations.models import IntegrationConnection, SecretReference  # noqa: F401
from app.modules.mcp.models import McpConnection  # noqa: F401
from app.modules.tools.models import ToolInstallation  # noqa: F401
from app.modules.workflows.models import Workflow, WorkflowRun, WorkflowVersion  # noqa: F401
from app.modules.workspaces.models import Workspace, WorkspaceInvitation, WorkspaceMember  # noqa: F401

target_metadata = Base.metadata
url = Settings().database_url
if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif context.config.attributes.get("connection") is not None:
    context.configure(
        connection=context.config.attributes["connection"], target_metadata=target_metadata
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url).connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
