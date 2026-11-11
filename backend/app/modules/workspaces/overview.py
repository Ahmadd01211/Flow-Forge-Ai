"""Workspace overview: setup progress, what needs attention, usage, recent work and triggers.

One role-aware read, so the page reflects the workspace with a single request. Every list is
bounded. Viewers see the same picture without decision rights, and only owners and admins get
the activity feed, matching the activity page.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.modules.agents.models import Agent, AgentVersion, standalone_versions, user_built
from app.modules.audit.models import AuditEvent
from app.modules.automations.models import WorkflowAutomation
from app.modules.deployments.models import Deployment
from app.modules.executions.models import AgentRun
from app.modules.identity.models import User
from app.modules.integrations.models import IntegrationConnection
from app.modules.workflows.models import Workflow, WorkflowPause, WorkflowRun, WorkflowVersion
from app.modules.workspaces.models import Workspace, WorkspaceInvitation, WorkspaceMember
from app.modules.workspaces.usage import summary

LIST_SIZE = 8
TREND_DAYS = 7
NEAR_LIMIT = Decimal("0.8")


def _any(db: Session, query) -> bool:
    return bool(db.scalar(select(exists(query))))


def _latest_versions(db: Session, workspace_id) -> list[WorkflowVersion]:
    """The newest published version of each workflow."""
    return db.scalars(
        select(WorkflowVersion)
        .where(WorkflowVersion.workspace_id == workspace_id)
        .distinct(WorkflowVersion.workflow_id)
        .order_by(WorkflowVersion.workflow_id, WorkflowVersion.number.desc())
        .limit(100)
    ).all()


def _step_label(graph: dict, node_id: str) -> str:
    node = next((item for item in graph.get("nodes", []) if item["id"] == node_id), None)
    return node["label"] if node else "Approval step"


def build(db: Session, workspace: Workspace, member: WorkspaceMember, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    ws = workspace.id
    usage = summary(db, workspace, now)
    latest = _latest_versions(db, ws)
    chat = [
        {"workflow_id": version.workflow_id, "name": version.name, "version_number": version.number}
        for version in latest
        if any(node["type"] == "chat_trigger" for node in version.graph.get("nodes", []))
    ][:LIST_SIZE]
    schedules = db.scalars(
        select(WorkflowAutomation)
        .where(WorkflowAutomation.workspace_id == ws, WorkflowAutomation.state == "active", WorkflowAutomation.kind == "schedule")
        .order_by(WorkflowAutomation.next_due_at.asc().nulls_last())
        .limit(LIST_SIZE)
    ).all()
    webhooks = db.scalars(
        select(WorkflowAutomation)
        .where(WorkflowAutomation.workspace_id == ws, WorkflowAutomation.state == "active", WorkflowAutomation.kind == "webhook")
        .order_by(WorkflowAutomation.created_at.desc())
        .limit(LIST_SIZE)
    ).all()
    deployments = db.scalar(
        select(func.count()).select_from(Deployment).where(Deployment.workspace_id == ws, Deployment.state == "active")
    ) or 0
    setup = {
        "provider_connected": _any(db, select(IntegrationConnection.id).where(
            IntegrationConnection.workspace_id == ws, IntegrationConnection.state == "active")),
        "published": bool(latest) or _any(db, select(AgentVersion.id).where(
            AgentVersion.workspace_id == ws, AgentVersion.purpose == "published", standalone_versions())),
        "succeeded": _any(db, select(WorkflowRun.id).where(WorkflowRun.workspace_id == ws, WorkflowRun.state == "completed"))
        or _any(db, select(AgentRun.id).where(AgentRun.workspace_id == ws, AgentRun.state == "completed")),
        "trigger": bool(schedules or webhooks or chat or deployments),
        "teammates": (db.scalar(select(func.count()).select_from(WorkspaceMember).where(WorkspaceMember.workspace_id == ws)) or 0) > 1
        or _any(db, select(WorkspaceInvitation.id).where(
            WorkspaceInvitation.workspace_id == ws, WorkspaceInvitation.consumed_at.is_(None), WorkspaceInvitation.expires_at > now)),
    }
    setup["complete"] = all(setup[key] for key in ("provider_connected", "published", "succeeded", "trigger"))
    return {
        "role": member.role,
        "can_decide": member.role in {"owner", "admin"},
        "counts": {
            "agents": db.scalar(select(func.count()).select_from(Agent).where(
                Agent.workspace_id == ws, Agent.archived_at.is_(None), user_built())) or 0,
            "workflows": db.scalar(select(func.count()).select_from(Workflow).where(Workflow.workspace_id == ws)) or 0,
        },
        "setup": setup,
        "usage": {**usage, **_success_today(db, ws, now)},
        "trend": _trend(db, ws, now),
        "attention": _attention(db, ws, member, usage, now),
        "recent_runs": _recent_runs(db, ws),
        "recent_edits": _recent_edits(db, ws, latest),
        "triggers": {
            "schedules": [
                {"id": row.id, "name": row.name, "next_due_at": row.next_due_at, "cron_expression": row.cron_expression,
                 "interval_seconds": row.interval_seconds, "timezone": row.timezone, "last_error_code": row.last_error_code}
                for row in schedules
            ],
            "webhooks": [{"id": row.id, "name": row.name, "last_error_code": row.last_error_code} for row in webhooks],
            "chat": chat,
            "deployments": deployments,
        },
        "activity": _activity(db, ws) if member.role in {"owner", "admin"} else None,
    }


def _success_today(db: Session, ws, now: datetime) -> dict:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    completed = failed = 0
    for model in (WorkflowRun, AgentRun):
        done, broken = db.execute(
            select(func.count().filter(model.state == "completed"), func.count().filter(model.state == "failed"))
            .where(model.workspace_id == ws, model.finished_at >= start)
        ).one()
        completed, failed = completed + done, failed + broken
    return {"completed_today": completed, "failed_today": failed}


def _trend(db: Session, ws, now: datetime) -> list[dict]:
    """Runs, failures and recorded spend per UTC day, oldest first, matching the daily limits."""
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=TREND_DAYS - 1)
    days = {(start + timedelta(days=offset)).date(): {"runs": 0, "failed": 0, "cost": Decimal(0)} for offset in range(TREND_DAYS)}
    for model in (WorkflowRun, AgentRun):
        day = func.date_trunc("day", func.timezone("UTC", model.created_at))
        rows = db.execute(
            select(day, func.count(), func.count().filter(model.state == "failed"), func.coalesce(func.sum(model.cost_usd), 0))
            .where(model.workspace_id == ws, model.created_at >= start)
            .group_by(day)
        ).all()
        for when, runs, failed, cost in rows:
            bucket = days.get(when.date())
            if bucket:
                bucket["runs"] += runs
                bucket["failed"] += failed
                bucket["cost"] += cost
    return [{"date": key.isoformat(), "runs": value["runs"], "failed": value["failed"], "cost_usd": str(value["cost"])} for key, value in days.items()]


def _attention(db: Session, ws, member: WorkspaceMember, usage: dict, now: datetime) -> dict:
    approvals = db.execute(
        select(WorkflowPause, WorkflowRun, WorkflowVersion)
        .join(WorkflowRun, WorkflowRun.id == WorkflowPause.run_id)
        .join(WorkflowVersion, WorkflowVersion.id == WorkflowRun.version_id)
        .where(WorkflowPause.workspace_id == ws, WorkflowPause.kind == "approval", WorkflowPause.state == "pending")
        .order_by(WorkflowPause.due_at)
        .limit(LIST_SIZE)
    ).all()
    pending = db.scalar(select(func.count()).select_from(WorkflowPause).where(
        WorkflowPause.workspace_id == ws, WorkflowPause.kind == "approval", WorkflowPause.state == "pending")) or 0
    since = now - timedelta(hours=24)
    failed = 0
    for model in (WorkflowRun, AgentRun):
        failed += db.scalar(select(func.count()).select_from(model).where(
            model.workspace_id == ws, model.state == "failed", model.finished_at >= since)) or 0
    # The newest published version of each user-built agent, and whether it can still run.
    agent_versions = db.execute(
        select(AgentVersion, IntegrationConnection)
        .outerjoin(IntegrationConnection, IntegrationConnection.id == AgentVersion.connection_id)
        .join(Agent, Agent.id == AgentVersion.agent_id)
        .where(AgentVersion.workspace_id == ws, AgentVersion.purpose == "published", user_built(), Agent.archived_at.is_(None))
        .distinct(AgentVersion.agent_id)
        .order_by(AgentVersion.agent_id, AgentVersion.number.desc())
    ).all()
    stale = [
        {"agent_id": version.agent_id, "name": version.name, "version_number": version.number,
         "reason": "provider_disconnected" if not connection or connection.state != "active" else "credential_changed"}
        for version, connection in agent_versions
        if not connection or connection.state != "active" or connection.credential_generation != version.credential_generation
    ][:LIST_SIZE]
    trigger_errors = db.scalars(
        select(WorkflowAutomation)
        .where(WorkflowAutomation.workspace_id == ws, WorkflowAutomation.state == "active", WorkflowAutomation.last_error_code.is_not(None))
        .limit(LIST_SIZE)
    ).all()
    budget = Decimal(usage["daily_budget_usd"])
    spend_ratio = Decimal(usage["committed_usd"]) / budget if budget > 0 else Decimal(0)
    run_ratio = Decimal(usage["accepted_runs"]) / usage["daily_run_limit"]
    return {
        "approvals": [
            {"pause_id": pause.id, "run_id": run.id, "node_id": pause.node_id, "workflow_name": version.name,
             "version_number": version.number, "step_label": _step_label(version.graph, pause.node_id),
             "prompt": pause.prompt, "created_at": pause.created_at, "due_at": pause.due_at,
             "requested_by_you": run.requested_by == member.user_id, "allow_requester": pause.allow_requester}
            for pause, run, version in approvals
        ],
        "approvals_total": pending,
        "failed_runs_24h": failed,
        "stale_agents": stale,
        "trigger_errors": [{"id": row.id, "name": row.name, "kind": row.kind, "last_error_code": row.last_error_code} for row in trigger_errors],
        "near_limits": {
            "spend": spend_ratio >= NEAR_LIMIT,
            "runs": run_ratio >= NEAR_LIMIT,
            "spend_ratio": float(min(spend_ratio, Decimal(9))),
            "run_ratio": float(min(run_ratio, Decimal(9))),
        },
    }


def _recent_runs(db: Session, ws) -> list[dict]:
    workflow_runs = db.execute(
        select(WorkflowRun, WorkflowVersion.name, WorkflowVersion.number, WorkflowVersion.workflow_id)
        .join(WorkflowVersion, WorkflowVersion.id == WorkflowRun.version_id)
        .where(WorkflowRun.workspace_id == ws)
        .order_by(WorkflowRun.created_at.desc())
        .limit(LIST_SIZE)
    ).all()
    agent_runs = db.execute(
        select(AgentRun, AgentVersion.name, AgentVersion.number, Agent.id, Agent.workflow_id, Agent.playground_for, Agent.system_role)
        .join(AgentVersion, AgentVersion.id == AgentRun.version_id)
        .join(Agent, Agent.id == AgentVersion.agent_id)
        .where(AgentRun.workspace_id == ws)
        .order_by(AgentRun.created_at.desc())
        .limit(LIST_SIZE)
    ).all()

    def common(run, kind, name, number, source, owner_id):
        duration = (run.finished_at - (run.started_at or run.created_at)).total_seconds() if run.finished_at else None
        return {
            "kind": kind, "id": run.id, "name": name, "version_number": number, "owner_id": owner_id,
            "state": run.state, "source": source, "error_code": run.error_code,
            "created_at": run.created_at, "finished_at": run.finished_at,
            "duration_seconds": round(duration, 1) if duration is not None else None,
            "cost_usd": str(run.cost_usd) if run.cost_usd is not None else None,
        }

    items = [common(run, "workflow", name, number, run.source, workflow_id) for run, name, number, workflow_id in workflow_runs]
    items += [
        common(run, "agent", name, number,
               "deployment" if run.deployment_id else "test" if workflow_id or playground_for or system_role else "manual",
               workflow_id or playground_for or agent_id)
        for run, name, number, agent_id, workflow_id, playground_for, system_role in agent_runs
    ]
    return sorted(items, key=lambda item: item["created_at"], reverse=True)[:LIST_SIZE]


def _recent_edits(db: Session, ws, latest: list[WorkflowVersion]) -> list[dict]:
    published = {version.workflow_id: version for version in latest}
    items = [
        {"kind": "workflow", "id": row.id, "name": row.name, "updated_at": row.updated_at,
         "status": "draft" if row.id not in published else "published" if published[row.id].source_revision == row.revision else "changed",
         "version_number": published[row.id].number if row.id in published else None}
        for row in db.scalars(select(Workflow).where(Workflow.workspace_id == ws).order_by(Workflow.updated_at.desc()).limit(LIST_SIZE)).all()
    ]
    agents = db.scalars(
        select(Agent)
        .where(Agent.workspace_id == ws, Agent.archived_at.is_(None), user_built())
        .order_by(Agent.updated_at.desc())
        .limit(LIST_SIZE)
    ).all()
    versions = {
        version.agent_id: version
        for version in db.scalars(
            select(AgentVersion)
            .where(AgentVersion.agent_id.in_([agent.id for agent in agents]), AgentVersion.purpose == "published")
            .distinct(AgentVersion.agent_id)
            .order_by(AgentVersion.agent_id, AgentVersion.number.desc())
        ).all()
    } if agents else {}
    items += [
        {"kind": "agent", "id": agent.id, "name": agent.name, "updated_at": agent.updated_at,
         "status": "draft" if agent.id not in versions else "published" if versions[agent.id].source_revision == agent.revision else "changed",
         "version_number": versions[agent.id].number if agent.id in versions else None}
        for agent in agents
    ]
    return sorted(items, key=lambda item: item["updated_at"], reverse=True)[:LIST_SIZE]


def _activity(db: Session, ws) -> list[dict]:
    rows = db.execute(
        select(AuditEvent, User.name)
        .outerjoin(User, User.id == AuditEvent.actor_id)
        .where(AuditEvent.workspace_id == ws)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(LIST_SIZE)
    ).all()
    return [
        {"id": event.id, "action": event.action, "actor_name": name or "Someone", "target_id": event.target_id,
         "details": event.details, "created_at": event.created_at}
        for event, name in rows
    ]
