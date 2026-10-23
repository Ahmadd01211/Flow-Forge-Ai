"""Deployment keys are one-way stored and bound to one immutable version."""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import Request
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import fail
from app.modules.agents.models import AgentVersion
from app.modules.audit.service import record
from app.modules.deployments.models import Deployment
from app.modules.executions.models import AgentRun
from app.modules.executions.service import MODEL_PRICES
from app.modules.integrations.models import IntegrationConnection
from app.modules.tools.models import ToolInstallation
from app.modules.workflows.models import WorkflowRun, WorkflowVersion
from app.modules.workflows.preview import validation
from app.modules.workflows.runtime import _executable
from app.modules.workflows.schemas import Graph


def public(row: Deployment) -> dict:
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "name": row.name,
        "kind": row.kind,
        "version_id": row.agent_version_id or row.workflow_version_id,
        "key_prefix": row.key_prefix,
        "state": row.state,
        "created_at": row.created_at,
        "rotated_at": row.rotated_at,
        "revoked_at": row.revoked_at,
    }


def _new_key() -> tuple[str, str, str]:
    raw = "ff_live_" + secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest(), raw[:16]


def _agent_ready(
    version: AgentVersion, connection: IntegrationConnection | None, installed: set[str]
) -> bool:
    return bool(
        (version.config.get("provider", "openai"), version.config.get("model_id")) in MODEL_PRICES
        and connection
        and connection.state == "active"
        and connection.credential_generation == version.credential_generation
        and version.config["model_id"] in connection.verified_models
        and not (set(version.config.get("tool_keys", [])) - installed)
    )


def eligible(db: Session, workspace_id: uuid.UUID, mcp_catalog_json: str = "[]") -> dict:
    agents = db.scalars(
        select(AgentVersion)
        .where(AgentVersion.workspace_id == workspace_id, AgentVersion.purpose == "published")
        .order_by(AgentVersion.created_at.desc())
        .limit(100)
    ).all()
    workflows = db.scalars(
        select(WorkflowVersion)
        .where(WorkflowVersion.workspace_id == workspace_id)
        .order_by(WorkflowVersion.created_at.desc())
        .limit(100)
    ).all()
    connections = {
        row.id: row
        for row in db.scalars(
            select(IntegrationConnection).where(IntegrationConnection.workspace_id == workspace_id)
        )
    }
    installed = set(
        db.scalars(
            select(ToolInstallation.tool_key).where(ToolInstallation.workspace_id == workspace_id)
        )
    )
    return {
        "items": [
            {"kind": "agent", "version_id": row.id, "name": row.name, "number": row.number}
            for row in agents
            if _agent_ready(row, connections.get(row.connection_id), installed)
        ]
        + [
            {"kind": "workflow", "version_id": row.id, "name": row.name, "number": row.number}
            for row in workflows
            if validation(db, workspace_id, Graph.model_validate(row.graph), mcp_catalog_json)["publishable"]
        ]
    }


def create(
    db: Session,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    name: str,
    kind: str,
    version_id: uuid.UUID,
    mcp_catalog_json: str = "[]",
) -> dict:
    if not name.strip():
        fail(422, "NAME_REQUIRED", "Give this deployment a name.")
    if kind == "agent":
        version = db.scalar(
            select(AgentVersion).where(
                AgentVersion.workspace_id == workspace_id,
                AgentVersion.id == version_id,
                AgentVersion.purpose == "published",
            )
        )
        connection = (
            db.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.workspace_id == workspace_id,
                    IntegrationConnection.id == version.connection_id,
                )
            )
            if version
            else None
        )
        installed = set(
            db.scalars(
                select(ToolInstallation.tool_key).where(
                    ToolInstallation.workspace_id == workspace_id
                )
            )
        )
        if not version or not _agent_ready(version, connection, installed):
            fail(422, "DEPLOYMENT_TARGET_INVALID", "Select an executable published agent version.")
    else:
        version = db.scalar(
            select(WorkflowVersion).where(
                WorkflowVersion.workspace_id == workspace_id, WorkflowVersion.id == version_id
            )
        )
        if not version:
            fail(422, "DEPLOYMENT_TARGET_INVALID", "Select a published workflow version.")
        _executable(db, workspace_id, Graph.model_validate(version.graph), mcp_catalog_json)
    raw, digest, prefix = _new_key()
    row = Deployment(
        workspace_id=workspace_id,
        name=name.strip(),
        kind=kind,
        agent_version_id=version_id if kind == "agent" else None,
        workflow_version_id=version_id if kind == "workflow" else None,
        key_hash=digest,
        key_prefix=prefix,
        state="active",
        created_by=actor_id,
    )
    db.add(row)
    db.flush()
    record(
        db,
        workspace_id,
        actor_id,
        "deployment.created",
        row.id,
        {"kind": kind, "version_id": str(version_id)},
    )
    db.commit()
    return {**public(row), "api_key": raw}


def find(
    db: Session, workspace_id: uuid.UUID, deployment_id: uuid.UUID, lock: bool = False
) -> Deployment:
    query = select(Deployment).where(
        Deployment.workspace_id == workspace_id, Deployment.id == deployment_id
    )
    row = db.scalar(query.with_for_update() if lock else query)
    if not row:
        fail(404, "NOT_FOUND", "Deployment not found.")
    return row


def rotate(
    db: Session, workspace_id: uuid.UUID, deployment_id: uuid.UUID, actor_id: uuid.UUID
) -> dict:
    row = find(db, workspace_id, deployment_id, lock=True)
    if row.state != "active":
        fail(409, "DEPLOYMENT_REVOKED", "This deployment has been revoked.")
    raw, row.key_hash, row.key_prefix = _new_key()
    row.rotated_at = datetime.now(UTC)
    record(db, workspace_id, actor_id, "deployment.rotated", row.id, {})
    db.commit()
    return {**public(row), "api_key": raw}


def revoke(
    db: Session, workspace_id: uuid.UUID, deployment_id: uuid.UUID, actor_id: uuid.UUID
) -> dict:
    row = find(db, workspace_id, deployment_id, lock=True)
    if row.state == "active":
        now = datetime.now(UTC)
        row.state = "revoked"
        row.revoked_at = now
        model = AgentRun if row.kind == "agent" else WorkflowRun
        runs = db.scalars(
            select(model)
            .where(
                model.workspace_id == workspace_id,
                model.deployment_id == row.id,
                model.state.in_(["queued", "running"]),
            )
            .with_for_update()
        ).all()
        for run in runs:
            run.cancel_requested_at = now
            if run.state == "queued":
                run.state = "cancelled"
                run.finished_at = now
        record(
            db,
            workspace_id,
            actor_id,
            "deployment.revoked",
            row.id,
            {"cancel_requested": len(runs)},
        )
        db.commit()
    return public(row)


def authenticate(db: Session, request: Request, deployment_id: uuid.UUID) -> Deployment:
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer ff_live_") or len(header) > 160:
        fail(401, "DEPLOYMENT_KEY_INVALID", "A valid deployment key is required.")
    row = db.scalar(select(Deployment).where(Deployment.id == deployment_id).with_for_update())
    candidate = hashlib.sha256(header.removeprefix("Bearer ").encode()).hexdigest()
    if not row or row.state != "active" or not hmac.compare_digest(row.key_hash, candidate):
        fail(401, "DEPLOYMENT_KEY_INVALID", "A valid deployment key is required.")
    return row


def throttle(request: Request, deployment_id: uuid.UUID, action: str) -> None:
    # Fail closed if Redis is unavailable. Keys never include the bearer token.
    key = f"deployment:{deployment_id}:{action}"
    try:
        pipe = request.app.state.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60, nx=True)
        count, _ = pipe.execute()
    except RedisError:
        fail(503, "RATE_LIMIT_UNAVAILABLE", "Invocation capacity is temporarily unavailable.")
    if count > (60 if action == "invoke" else 240):
        fail(429, "RATE_LIMITED", "This deployment has reached its request limit.")
