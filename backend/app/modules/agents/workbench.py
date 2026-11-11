"""Agent builder workbench: library summaries, live draft chat, published chat, memory and examples."""

import json
import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.credentials import decrypt_secret, encrypt_secret, load_master_key
from app.core.db import get_db
from app.core.errors import fail
from app.core.json_contracts import bounded_json, example_errors
from app.modules.agents import service
from app.modules.agents.evaluations import EvaluationSuite
from app.modules.agents.managed import playground_version
from app.modules.agents.memory import TURN_GENERATION, _hash
from app.modules.agents.models import Agent, AgentVersion, ConversationTurn, user_built
from app.modules.agents.schemas import AgentConfig
from app.modules.audit.service import record
from app.modules.executions import service as executions
from app.modules.executions.models import AgentRun
from app.modules.executions.schemas import RunCreate
from app.modules.identity.service import check_csrf
from app.modules.integrations.models import IntegrationConnection
from app.modules.workflows.chat import CHAT_SAMPLE, ChatMessage
from app.modules.workspaces.service import authorize

router = APIRouter(prefix="/workspaces/{workspace_id}/agents", tags=["agent-workbench"])
EXAMPLE_SUITE = "Saved from chat"
TRY_MESSAGES = {
    "PROVIDER_REQUIRED": "Connect and verify this model's provider in Integrations to start testing.",
    "INSTRUCTIONS_REQUIRED": "Add instructions in Persona to start testing.",
    "MODEL_UNSUPPORTED": "Choose a model from the provider's verified list in Brain.",
    "TOOLS_RUNTIME_UNSUPPORTED": "This model can't call tools. Pick a model with the Tools badge, or switch the tools off.",
}


class TryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: AgentConfig
    input: dict


class AssistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: Literal["improve", "draft", "examples"]
    provider: Literal["openai", "openrouter", "anthropic", "gemini", "deepseek"]
    model_id: str = Field(min_length=1, max_length=200)
    context: dict


class ExampleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="", max_length=100)
    input: dict
    expected_output: dict


def _latest_published(db: Session, agent_ids: list[uuid.UUID]) -> dict[uuid.UUID, AgentVersion]:
    if not agent_ids:
        return {}
    return {
        version.agent_id: version
        for version in db.scalars(
            select(AgentVersion)
            .where(AgentVersion.agent_id.in_(agent_ids), AgentVersion.purpose == "published")
            .distinct(AgentVersion.agent_id)
            .order_by(AgentVersion.agent_id, AgentVersion.number.desc())
        ).all()
    }


def _chat_ready(version: AgentVersion | None) -> bool:
    return bool(version) and not example_errors(version.config["input_schema"], CHAT_SAMPLE, "input")


@router.post("/assist", status_code=202, dependencies=[Depends(check_csrf)])
def assist(
    workspace_id: uuid.UUID,
    body: AssistRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    """Start a builder AI helper as a normal, budgeted agent run with the chosen model."""
    from app.modules.agents.assist import assistant_version

    _, member = authorize(request, db, workspace_id, write=True)
    bounded_json(body.context, max_bytes=40000)
    settings = request.app.state.settings
    try:
        version = assistant_version(db, workspace_id, body.task, body.provider, body.model_id, member.user_id, settings.mcp_catalog_json)
    except HTTPException as error:
        detail = error.detail if isinstance(error.detail, dict) else {}
        fail(error.status_code, detail.get("code", "ASSIST_UNAVAILABLE"), TRY_MESSAGES.get(detail.get("code"), detail.get("message", "The AI helper can't run with this model.")))
    master = load_master_key(settings.credential_key_path)
    run, _ = executions.submit(
        db, workspace_id, member.user_id, RunCreate(version_id=version.id, input=body.context),
        idempotency_key, master, raw_catalog=settings.mcp_catalog_json,
    )
    return {"run": executions.public_run(run, master)}


@router.get("/library")
def library(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    """Every user-built agent with what it can do, whether it is published and how it has run."""
    authorize(request, db, workspace_id)
    agents = db.scalars(
        select(Agent)
        .where(Agent.workspace_id == workspace_id, Agent.archived_at.is_(None), user_built())
        .order_by(Agent.updated_at.desc(), Agent.id.desc())
        .limit(100)
    ).all()
    ids = [agent.id for agent in agents]
    published = _latest_published(db, ids)
    connections = {row.id: row for row in db.scalars(select(IntegrationConnection).where(IntegrationConnection.workspace_id == workspace_id))}
    since = datetime.now(UTC) - timedelta(days=7)
    week = {
        agent_id: (completed, failed)
        for agent_id, completed, failed in db.execute(
            select(
                AgentVersion.agent_id,
                func.count().filter(AgentRun.state == "completed", AgentRun.created_at >= since),
                func.count().filter(AgentRun.state == "failed", AgentRun.created_at >= since),
            )
            .join(AgentVersion, AgentVersion.id == AgentRun.version_id)
            .where(AgentRun.workspace_id == workspace_id, AgentVersion.agent_id.in_(ids))
            .group_by(AgentVersion.agent_id)
        ).all()
    } if ids else {}
    last = {
        agent_id: (state, created)
        for agent_id, state, created in db.execute(
            select(AgentVersion.agent_id, AgentRun.state, AgentRun.created_at)
            .join(AgentVersion, AgentVersion.id == AgentRun.version_id)
            .where(AgentRun.workspace_id == workspace_id, AgentVersion.agent_id.in_(ids))
            .distinct(AgentVersion.agent_id)
            .order_by(AgentVersion.agent_id, AgentRun.created_at.desc())
        ).all()
    } if ids else {}
    items = []
    for agent in agents:
        config = agent.config
        version = published.get(agent.id)
        connection = connections.get(version.connection_id) if version else None
        runnable = bool(version and connection and connection.state == "active" and connection.credential_generation == version.credential_generation)
        completed, failed = week.get(agent.id, (0, 0))
        state, created = last.get(agent.id, (None, None))
        items.append({
            "id": agent.id,
            "name": agent.name,
            "description": agent.description,
            "revision": agent.revision,
            "updated_at": agent.updated_at,
            "provider": config.get("provider", "openai"),
            "model_id": config.get("model_id", ""),
            "tools": {
                "builtin": config.get("tool_keys", []),
                "mcp_servers": sorted({grant["server_id"] for grant in config.get("mcp_tools", [])}),
                "http": [grant.get("name") or "API" for grant in config.get("http_tools", [])],
                "count": len(config.get("tool_keys", [])) + len(config.get("mcp_tools", [])) + len(config.get("http_tools", [])),
            },
            "memory": bool(config.get("memory")),
            "status": "draft" if not version else "published" if version.source_revision == agent.revision else "changed",
            "published": {"version_id": version.id, "number": version.number, "runnable": runnable, "chat_ready": _chat_ready(version)} if version else None,
            "last_run": {"state": state, "created_at": created} if state else None,
            "week": {"completed": completed, "failed": failed},
        })
    return {"items": items}


@router.get("/{agent_id}/performance")
def performance(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    request: Request,
    days: int = Query(default=7, ge=1, le=90),
    include_tests: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    """How the agent's runs went over the last `days`: volume, success, speed, cost, tools, errors, feedback."""
    from app.modules.executions.trace import performance as summarize

    authorize(request, db, workspace_id)
    return summarize(db, workspace_id, service.get_agent(db, workspace_id, agent_id), days, include_tests)


@router.post("/{agent_id}/try", status_code=202, dependencies=[Depends(check_csrf)])
def try_draft(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: TryRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    """Run the editor's current, possibly unsaved, settings once as a normal budgeted agent run."""
    _, member = authorize(request, db, workspace_id, write=True)
    owner = service.get_agent(db, workspace_id, agent_id, lock=True)
    settings = request.app.state.settings
    try:
        version = playground_version(db, workspace_id, owner, body.config.model_dump(), member.user_id, settings.mcp_catalog_json)
    except HTTPException as error:
        # The checks are shared with publishing; word them for a test chat.
        detail = error.detail if isinstance(error.detail, dict) else {}
        message = TRY_MESSAGES.get(detail.get("code"), detail.get("message", "This draft can't run yet."))
        fail(error.status_code, detail.get("code", "TRY_UNAVAILABLE"), message)
    master = load_master_key(settings.credential_key_path)
    run, _ = executions.submit(
        db, workspace_id, member.user_id, RunCreate(version_id=version.id, input=body.input),
        idempotency_key, master, raw_catalog=settings.mcp_catalog_json,
    )
    return {"run": executions.public_run(run, master)}


@router.post("/{agent_id}/chat", status_code=202, dependencies=[Depends(check_csrf)])
def chat(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: ChatMessage,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> dict:
    """Send one message to the agent's latest published version."""
    _, member = authorize(request, db, workspace_id, write=True)
    service.get_agent(db, workspace_id, agent_id)
    version = _latest_published(db, [agent_id]).get(agent_id)
    if not version:
        fail(409, "AGENT_NOT_PUBLISHED", "Publish this agent before chatting with it.")
    if not _chat_ready(version):
        fail(409, "AGENT_NOT_CHAT", "This agent's input does not accept conversation_id and message. Use the Chat input preset and republish.")
    conversation_id = body.conversation_id or str(uuid.uuid4())
    settings = request.app.state.settings
    master = load_master_key(settings.credential_key_path)
    run, created = executions.submit(
        db, workspace_id, member.user_id,
        RunCreate(version_id=version.id, input={"conversation_id": conversation_id, "message": body.message}),
        idempotency_key, master, raw_catalog=settings.mcp_catalog_json,
    )
    if not created:
        response.status_code = 200
    return {"conversation_id": conversation_id, "version_id": version.id, "run": executions.public_run(run, master)}


def _memory_owner(request: Request, db: Session, workspace_id: uuid.UUID, agent_id: uuid.UUID):
    _, member = authorize(request, db, workspace_id)
    if member.role not in {"owner", "admin"}:
        fail(403, "FORBIDDEN", "An owner or admin can read or forget remembered conversations.")
    service.get_agent(db, workspace_id, agent_id)
    return member


@router.get("/{agent_id}/memory")
def memory(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    request: Request,
    conversation_id: str | None = Query(default=None, min_length=1, max_length=200),
    db: Session = Depends(get_db),
) -> dict:
    """How many conversations are remembered, and the stored turns of one conversation by its ID."""
    _memory_owner(request, db, workspace_id, agent_id)
    conversations = db.scalar(
        select(func.count(func.distinct(ConversationTurn.conversation_hash))).where(
            ConversationTurn.workspace_id == workspace_id, ConversationTurn.agent_id == agent_id)
    ) or 0
    turns = []
    if conversation_id:
        master = load_master_key(request.app.state.settings.credential_key_path)
        rows = db.scalars(
            select(ConversationTurn)
            .where(ConversationTurn.workspace_id == workspace_id, ConversationTurn.conversation_hash == _hash(agent_id, conversation_id))
            .order_by(ConversationTurn.sequence)
            .limit(40)
        ).all()
        turns = [
            {"role": row.role, "created_at": row.created_at, "expires_at": row.expires_at,
             "content": json.loads(decrypt_secret(master, workspace_id, row.id, TURN_GENERATION, row.nonce, row.ciphertext))}
            for row in rows
        ]
    return {"conversations": conversations, "turns": turns}


@router.delete("/{agent_id}/memory", dependencies=[Depends(check_csrf)])
def forget(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    request: Request,
    conversation_id: str | None = Query(default=None, min_length=1, max_length=200),
    db: Session = Depends(get_db),
) -> dict:
    """Forget one conversation, or every conversation this agent remembers."""
    member = _memory_owner(request, db, workspace_id, agent_id)
    query = delete(ConversationTurn).where(ConversationTurn.workspace_id == workspace_id, ConversationTurn.agent_id == agent_id)
    if conversation_id:
        query = query.where(ConversationTurn.conversation_hash == _hash(agent_id, conversation_id))
    deleted = db.execute(query).rowcount or 0
    record(db, workspace_id, member.user_id, "agent.memory_forgotten", agent_id, {"scope": "conversation" if conversation_id else "all", "turns": deleted})
    db.commit()
    return {"deleted_turns": deleted}


@router.post("/{agent_id}/duplicate", status_code=201, dependencies=[Depends(check_csrf)])
def duplicate(workspace_id: uuid.UUID, agent_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    authorize(request, db, workspace_id, write=True)
    source = service.get_agent(db, workspace_id, agent_id)
    copy = Agent(
        workspace_id=workspace_id, name=f"{source.name[:93]} (copy)", description=source.description,
        config=deepcopy(source.config),
    )
    db.add(copy)
    db.commit()
    return service.serialize(copy)


@router.post("/{agent_id}/examples", status_code=201, dependencies=[Depends(check_csrf)])
def save_example(
    workspace_id: uuid.UUID, agent_id: uuid.UUID, body: ExampleCreate, request: Request, db: Session = Depends(get_db),
) -> dict:
    """Append a chat exchange to the agent's "Saved from chat" regression examples."""
    _, member = authorize(request, db, workspace_id, write=True)
    service.get_agent(db, workspace_id, agent_id)
    master = load_master_key(request.app.state.settings.credential_key_path)
    suite = db.scalar(
        select(EvaluationSuite)
        .where(EvaluationSuite.workspace_id == workspace_id, EvaluationSuite.agent_id == agent_id, EvaluationSuite.name == EXAMPLE_SUITE)
        .with_for_update()
    )
    cases = json.loads(decrypt_secret(master, workspace_id, suite.id, 1, suite.nonce, suite.ciphertext)) if suite else []
    if len(cases) >= 20:
        fail(422, "EXAMPLE_LIMIT", "This agent already has 20 saved examples. Remove some in Test examples first.")
    cases.append({"name": body.name.strip() or f"Chat example {len(cases) + 1}", "input": body.input, "expected_output": body.expected_output})
    bounded_json(cases, max_bytes=65536)
    if not suite:
        suite = EvaluationSuite(id=uuid.uuid4(), workspace_id=workspace_id, agent_id=agent_id, name=EXAMPLE_SUITE)
        db.add(suite)
    suite.nonce, suite.ciphertext = encrypt_secret(master, workspace_id, suite.id, 1, json.dumps(cases))
    record(db, workspace_id, member.user_id, "agent.example_saved", suite.id, {"agent_id": str(agent_id), "case_count": len(cases)})
    db.commit()
    return {"suite_id": suite.id, "count": len(cases)}
