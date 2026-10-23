import hashlib
import json
import uuid
from copy import deepcopy
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import fail
from app.core.json_contracts import example_errors, validate_user_schema
from app.modules.agents.models import Agent, AgentVersion
from app.modules.agents.readiness import assess
from app.modules.agents.schemas import (
    AgentConfig,
    AgentCreate,
    AgentUpdate,
    ExampleRequest,
    RestoreRequest,
    SnapshotCreate,
)
from app.modules.audit.service import record
from app.modules.integrations.service import get_connection


def get_agent(
    db: Session,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    lock: bool = False,
    include_archived: bool = False,
) -> Agent:
    query = select(Agent).where(Agent.workspace_id == workspace_id, Agent.id == agent_id)
    if not include_archived:
        query = query.where(Agent.archived_at.is_(None))
    agent = db.scalar(query.with_for_update() if lock else query)
    if not agent:
        fail(404, "NOT_FOUND", "Agent not found.")
    return agent


def validate_schemas(config: dict) -> None:
    for name in ["input_schema", "output_schema"]:
        validate_user_schema(config[name])


def serialize(agent: Agent) -> dict:
    return {
        key: getattr(agent, key)
        for key in ["id", "workspace_id", "name", "description", "config", "revision", "updated_at"]
    }


def list_drafts(db: Session, workspace_id: uuid.UUID) -> dict:
    rows = db.scalars(
        select(Agent)
        .where(Agent.workspace_id == workspace_id, Agent.archived_at.is_(None))
        .order_by(Agent.updated_at.desc(), Agent.id.desc())
        .limit(100)
    ).all()
    return {"items": [serialize(a) for a in rows], "next_cursor": None}


def create_draft(db: Session, workspace_id: uuid.UUID, body: AgentCreate) -> dict:
    config = body.config.model_dump()
    validate_schemas(config)
    agent = Agent(
        workspace_id=workspace_id, name=body.name, description=body.description, config=config
    )
    db.add(agent)
    db.commit()
    return serialize(agent)


def check_revision(agent: Agent, expected_revision: int) -> None:
    if agent.revision != expected_revision:
        fail(
            409,
            "REVISION_CONFLICT",
            "This agent changed elsewhere. Reload before saving or creating a snapshot.",
        )


def update_draft(
    db: Session, workspace_id: uuid.UUID, agent_id: uuid.UUID, body: AgentUpdate
) -> dict:
    agent = get_agent(db, workspace_id, agent_id, lock=True)
    check_revision(agent, body.expected_revision)
    config = body.config.model_dump()
    validate_schemas(config)
    agent.name, agent.description, agent.config = body.name, body.description, config
    agent.revision += 1
    db.commit()
    return serialize(agent)


def archive_draft(db: Session, workspace_id: uuid.UUID, agent_id: uuid.UUID) -> dict:
    agent = get_agent(db, workspace_id, agent_id, lock=True)
    agent.archived_at = datetime.now(UTC)
    db.commit()
    return {"id": agent.id, "archived": True}


def config_hash(config: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            config, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def snapshot(
    db: Session,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    actor_id: uuid.UUID,
    body: SnapshotCreate,
) -> tuple[AgentVersion, bool]:
    agent = get_agent(db, workspace_id, agent_id, lock=True)
    check_revision(agent, body.expected_revision)
    existing = db.scalar(
        select(AgentVersion).where(
            AgentVersion.workspace_id == workspace_id,
            AgentVersion.agent_id == agent_id,
            AgentVersion.source_revision == agent.revision,
            AgentVersion.purpose == "test",
        )
    )
    if existing:
        return existing, False
    config = AgentConfig.model_validate(agent.config).model_dump()
    validate_schemas(config)
    if not config["instructions"].strip():
        fail(422, "INSTRUCTIONS_REQUIRED", "Add instructions before creating a test snapshot.")
    number = (
        db.scalar(select(func.max(AgentVersion.number)).where(AgentVersion.agent_id == agent.id))
        or 0
    ) + 1
    version = AgentVersion(
        workspace_id=workspace_id,
        agent_id=agent.id,
        number=number,
        purpose="test",
        source_revision=agent.revision,
        schema_version=config["schema_version"],
        name=agent.name,
        description=agent.description,
        config=deepcopy(config),
        config_hash=config_hash(config),
        change_summary=body.change_summary.strip(),
        created_by=actor_id,
    )
    db.add(version)
    db.flush()
    record(
        db,
        workspace_id,
        actor_id,
        "agent.snapshot_created",
        version.id,
        {
            "agent_id": str(agent.id),
            "number": number,
            "source_revision": agent.revision,
            "purpose": "test",
        },
    )
    db.commit()
    return version, True


def publish(
    db: Session,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    actor_id: uuid.UUID,
    body: SnapshotCreate,
) -> tuple[AgentVersion, bool]:
    agent = get_agent(db, workspace_id, agent_id, lock=True)
    check_revision(agent, body.expected_revision)
    existing = db.scalar(
        select(AgentVersion).where(
            AgentVersion.agent_id == agent_id,
            AgentVersion.source_revision == agent.revision,
            AgentVersion.purpose == "published",
        )
    )
    if existing:
        return existing, False
    config = AgentConfig.model_validate(agent.config).model_dump()
    connection = get_connection(db, workspace_id, config["provider"], lock=True)
    checked = assess(db, workspace_id, config, connection)
    if checked["errors"]:
        first = checked["errors"][0]
        fail(409 if first["code"] in {"PROVIDER_REQUIRED", "TOOL_NOT_APPROVED"} else 422, first["code"], first["message"])
    number = (
        db.scalar(select(func.max(AgentVersion.number)).where(AgentVersion.agent_id == agent.id))
        or 0
    ) + 1
    version = AgentVersion(
        workspace_id=workspace_id,
        agent_id=agent.id,
        connection_id=connection.id,
        credential_generation=connection.credential_generation,
        number=number,
        purpose="published",
        source_revision=agent.revision,
        schema_version=config["schema_version"],
        name=agent.name,
        description=agent.description,
        config=deepcopy(config),
        config_hash=config_hash(config),
        change_summary=body.change_summary.strip(),
        created_by=actor_id,
    )
    db.add(version)
    db.flush()
    record(
        db,
        workspace_id,
        actor_id,
        "agent.published",
        version.id,
        {
            "agent_id": str(agent.id),
            "number": number,
            "source_revision": agent.revision,
            "connection_id": str(connection.id),
            "provider": config["provider"],
            "model_id": config["model_id"],
        },
    )
    db.commit()
    return version, True


def get_version(
    db: Session, workspace_id: uuid.UUID, agent_id: uuid.UUID, version_id: uuid.UUID
) -> AgentVersion:
    version = db.scalar(
        select(AgentVersion).where(
            AgentVersion.workspace_id == workspace_id,
            AgentVersion.agent_id == agent_id,
            AgentVersion.id == version_id,
        )
    )
    if not version:
        fail(404, "NOT_FOUND", "Agent version not found.")
    return version


def list_versions(
    db: Session,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    cursor: str | None,
    limit: int,
    purpose: str | None,
) -> dict:
    get_agent(db, workspace_id, agent_id, include_archived=True)
    query = select(AgentVersion).where(
        AgentVersion.workspace_id == workspace_id, AgentVersion.agent_id == agent_id
    )
    if cursor:
        if not cursor.isascii() or not cursor.isdecimal() or len(cursor) > 10 or int(cursor) < 1:
            fail(422, "CURSOR_INVALID", "The version cursor is invalid.")
        query = query.where(AgentVersion.number < int(cursor))
    if purpose:
        query = query.where(AgentVersion.purpose == purpose)
    rows = list(db.scalars(query.order_by(AgentVersion.number.desc()).limit(limit + 1)))
    return {
        "items": rows[:limit],
        "next_cursor": str(rows[limit - 1].number) if len(rows) > limit else None,
    }


def restore_version(
    db: Session,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    actor_id: uuid.UUID,
    body: RestoreRequest,
) -> dict:
    agent = get_agent(db, workspace_id, agent_id, lock=True)
    check_revision(agent, body.expected_revision)
    version = get_version(db, workspace_id, agent_id, body.version_id)
    # Revalidate old snapshots under today's supported contract before restoring.
    config = AgentConfig.model_validate(version.config).model_dump()
    validate_schemas(config)
    agent.name, agent.description, agent.config = (
        version.name,
        version.description,
        deepcopy(config),
    )
    agent.revision += 1
    record(
        db,
        workspace_id,
        actor_id,
        "agent.version_restored",
        agent.id,
        {"version_id": str(version.id), "new_revision": agent.revision},
    )
    db.commit()
    return serialize(agent)


def validate_example(version: AgentVersion, body: ExampleRequest) -> dict:
    validate_schemas(version.config)
    input_errors = example_errors(version.config["input_schema"], body.input, "input")
    output_checked = "output" in body.model_fields_set
    output_errors = (
        example_errors(version.config["output_schema"], body.output, "output")
        if output_checked
        else []
    )
    return {
        "version_id": version.id,
        "config_hash": version.config_hash,
        "input_valid": not input_errors,
        "output_valid": not output_errors if output_checked else None,
        "errors": input_errors + output_errors,
        "scope": "contract",
        "model_called": False,
    }
