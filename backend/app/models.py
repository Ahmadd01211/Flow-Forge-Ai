"""ORM registration at process composition roots; no application/service startup side effects."""

from app.modules.agents.evaluations import EvaluationSuite  # noqa: F401
from app.modules.agents.models import Agent, AgentVersion  # noqa: F401
from app.modules.audit.models import AuditEvent  # noqa: F401
from app.modules.automations.models import WorkflowAutomation  # noqa: F401
from app.modules.deployments.models import Deployment  # noqa: F401
from app.modules.executions.models import AgentRun, RunEvent  # noqa: F401
from app.modules.http_tools.models import HttpTool  # noqa: F401
from app.modules.identity.models import AccountToken, EmailDelivery, User, UserSession  # noqa: F401
from app.modules.integrations.models import IntegrationConnection, SecretReference  # noqa: F401
from app.modules.mcp.models import McpConnection  # noqa: F401
from app.modules.templates.models import UserTemplate  # noqa: F401
from app.modules.tools.models import ToolInstallation  # noqa: F401
from app.modules.workflows.models import Workflow, WorkflowRun, WorkflowVersion  # noqa: F401
from app.modules.workspaces.models import Workspace, WorkspaceInvitation, WorkspaceMember  # noqa: F401
