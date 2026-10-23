"""Durable execution for published linear workflows using pure local tools."""

import hashlib
import json
import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.credentials import decrypt_secret, encrypt_secret, load_master_key
from app.core.errors import fail
from app.core.json_contracts import bounded_json, example_errors
from app.modules.agents.models import AgentVersion
from app.modules.audit.service import record
from app.modules.executions.runtime import ProviderFailure, generate, generate_openai_with_tools
from app.modules.executions.service import MAX_INPUT_BYTES, MAX_OUTPUT_TOKENS, MODEL_PRICES
from app.modules.integrations.models import IntegrationConnection, SecretReference
from app.modules.mcp.catalog import catalog
from app.modules.mcp.client import call_tool
from app.modules.mcp.models import McpConnection
from app.modules.mcp.service import schema_hash
from app.modules.tools.models import ToolInstallation
from app.modules.workflows.models import Workflow, WorkflowRun, WorkflowVersion
from app.modules.workflows.preview import run_preview, validation
from app.modules.workflows.schemas import Graph
from app.modules.workspaces.models import Workspace


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _executable(db: Session, workspace_id: uuid.UUID, graph: Graph, mcp_catalog_json: str = "[]") -> None:
    try:
        budget = Decimal(graph.limits["max_cost_usd"])
    except (KeyError, TypeError, ValueError, ArithmeticError):
        fail(422, "WORKFLOW_BUDGET_INVALID", "Set a valid workflow budget.")
    if not budget.is_finite() or budget <= 0 or budget > 10:
        fail(422, "WORKFLOW_BUDGET_INVALID", "Set a workflow budget between $0 and $10.")
    checked = validation(db, workspace_id, graph, mcp_catalog_json)
    if not checked["valid"]:
        fail(422, "WORKFLOW_INVALID", checked["errors"][0]["message"])
    if not checked["publishable"]:
        fail(
            422,
            "RUNTIME_UNSUPPORTED",
            "This workflow shape is not yet supported for published runs.",
        )


def publish(
    db: Session,
    workspace_id: uuid.UUID,
    workflow_id: uuid.UUID,
    actor_id: uuid.UUID,
    expected_revision: int,
    mcp_catalog_json: str = "[]",
) -> WorkflowVersion:
    row = db.scalar(
        select(Workflow)
        .where(Workflow.workspace_id == workspace_id, Workflow.id == workflow_id)
        .with_for_update()
    )
    if not row:
        fail(404, "NOT_FOUND", "Workflow not found.")
    if row.revision != expected_revision:
        fail(409, "REVISION_CONFLICT", "Save the latest draft before publishing.")
    existing = db.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == row.id, WorkflowVersion.source_revision == row.revision
        )
    )
    if existing:
        return existing
    graph = Graph.model_validate(row.graph)
    _executable(db, workspace_id, graph, mcp_catalog_json)
    for node in graph.nodes:
        if node.type == "mcp_tool":
            connection = db.scalar(select(McpConnection).where(
                McpConnection.workspace_id == workspace_id,
                McpConnection.server_id == node.config["server_id"],
            ))
            snapshot = next(item for item in connection.tool_snapshots if item["name"] == node.config["tool_name"])
            node.config = {**node.config, "connection_generation": connection.generation,
                           "input_schema_hash": schema_hash(snapshot["input_schema"])}
    number = (
        db.scalar(
            select(func.max(WorkflowVersion.number)).where(WorkflowVersion.workflow_id == row.id)
        )
        or 0
    ) + 1
    data = graph.model_dump()
    version = WorkflowVersion(
        workspace_id=workspace_id,
        workflow_id=row.id,
        number=number,
        source_revision=row.revision,
        name=row.name,
        graph=deepcopy(data),
        graph_hash=hashlib.sha256(_canonical(data).encode()).hexdigest(),
        created_by=actor_id,
    )
    db.add(version)
    db.flush()
    record(
        db,
        workspace_id,
        actor_id,
        "workflow.published",
        version.id,
        {"workflow_id": str(row.id), "number": number},
    )
    db.commit()
    return version


def public_version(version: WorkflowVersion) -> dict:
    return {
        key: getattr(version, key)
        for key in (
            "id",
            "workflow_id",
            "workspace_id",
            "number",
            "source_revision",
            "name",
            "graph_hash",
            "created_at",
        )
    }


def submit(
    db: Session,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    version_id: uuid.UUID,
    input_data: dict,
    idempotency_key: str,
    master: bytes,
    deployment_id: uuid.UUID | None = None,
    mcp_catalog_json: str = "[]",
) -> tuple[WorkflowRun, bool]:
    if not 8 <= len(idempotency_key) <= 128 or any(ch.isspace() for ch in idempotency_key):
        fail(
            422, "IDEMPOTENCY_KEY_INVALID", "Use an 8–128 character idempotency key without spaces."
        )
    bounded_json(input_data, max_bytes=65536)
    db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    key_hash = hashlib.sha256(
        (f"{deployment_id}:{idempotency_key}" if deployment_id else idempotency_key).encode()
    ).hexdigest()
    request_hash = hashlib.sha256(
        _canonical({"version_id": str(version_id), "input": input_data}).encode()
    ).hexdigest()
    existing = db.scalar(
        select(WorkflowRun).where(
            WorkflowRun.workspace_id == workspace_id,
            WorkflowRun.requested_by == actor_id,
            WorkflowRun.idempotency_key_hash == key_hash,
        )
    )
    if existing:
        if existing.request_hash != request_hash:
            fail(409, "IDEMPOTENCY_CONFLICT", "This key was used for another workflow request.")
        return existing, False
    version = db.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workspace_id == workspace_id, WorkflowVersion.id == version_id
        )
    )
    if not version:
        fail(404, "NOT_FOUND", "Published workflow version not found.")
    graph = Graph.model_validate(version.graph)
    _executable(db, workspace_id, graph, mcp_catalog_json)
    if example_errors(graph.input_schema, input_data, "input"):
        fail(422, "INPUT_SCHEMA_INVALID", "Input does not match this workflow version.")
    count = (
        db.scalar(
            select(func.count())
            .select_from(WorkflowRun)
            .where(
                WorkflowRun.workspace_id == workspace_id,
                WorkflowRun.state.in_(["queued", "running"]),
            )
        )
        or 0
    )
    if count >= 2:
        fail(429, "RUN_CONCURRENCY_LIMIT", "This workspace already has two active workflow runs.")
    run_id = uuid.uuid4()
    nonce, ciphertext = encrypt_secret(master, workspace_id, run_id, 1, _canonical(input_data))
    run = WorkflowRun(
        id=run_id,
        workspace_id=workspace_id,
        version_id=version_id,
        deployment_id=deployment_id,
        requested_by=actor_id,
        idempotency_key_hash=key_hash,
        request_hash=request_hash,
        state="queued",
        input_nonce=nonce,
        input_ciphertext=ciphertext,
        deadline_at=datetime.now(UTC) + timedelta(seconds=30 if any(n.type in {"agent", "mcp_tool"} for n in graph.nodes) else 15),
    )
    db.add(run)
    record(
        db,
        workspace_id,
        actor_id,
        "workflow_run.submitted",
        run.id,
        {"version_id": str(version_id)},
    )
    db.commit()
    return run, True


def get_run(
    db: Session, workspace_id: uuid.UUID, run_id: uuid.UUID, lock: bool = False
) -> WorkflowRun:
    query = select(WorkflowRun).where(
        WorkflowRun.workspace_id == workspace_id, WorkflowRun.id == run_id
    )
    run = db.scalar(query.with_for_update() if lock else query)
    if not run:
        fail(404, "NOT_FOUND", "Workflow run not found.")
    return run


def public_run(run: WorkflowRun, master: bytes) -> dict:
    result = (
        json.loads(
            decrypt_secret(
                master, run.workspace_id, run.id, 2, run.output_nonce, run.output_ciphertext
            )
        )
        if run.output_nonce and run.output_ciphertext
        else None
    )
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "version_id": run.version_id,
        "state": run.state,
        "output": result["output"] if result else None,
        "steps": result["steps"] if result else None,
        "error_code": run.error_code,
        "cost_usd": str(run.cost_usd) if run.cost_usd is not None else None,
        "uncertain_cost_usd": str(run.uncertain_cost_usd) if run.uncertain_cost_usd is not None else None,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "cancel_requested": run.cancel_requested_at is not None,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


def cancel(
    db: Session, workspace_id: uuid.UUID, run_id: uuid.UUID, actor_id: uuid.UUID
) -> WorkflowRun:
    run = get_run(db, workspace_id, run_id, lock=True)
    if run.state in ("completed", "failed", "cancelled"):
        return run
    run.cancel_requested_at = datetime.now(UTC)
    if run.state == "queued":
        run.state = "cancelled"
        run.finished_at = run.cancel_requested_at
    record(
        db, workspace_id, actor_id, "workflow_run.cancel_requested", run.id, {"state": run.state}
    )
    db.commit()
    return run


def _agent_handler(sessions, identity, token, workspace_id, master, graph, settings):
    def active() -> bool:
        with sessions() as db:
            current = db.scalar(select(WorkflowRun).where(WorkflowRun.id == identity))
            return bool(current and current.state == "running" and current.claim_token == token and not current.cancel_requested_at and datetime.now(UTC) < current.deadline_at)

    def call(node, data):
        with sessions() as db:
            run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == identity).with_for_update())
            if not run or run.state != "running" or run.claim_token != token or run.cancel_requested_at:
                fail(409, "RUN_INTERRUPTED", "This workflow run was interrupted.")
            now = datetime.now(UTC)
            if now >= run.deadline_at:
                fail(408, "RUN_TIMEOUT", "This workflow run timed out.")
            try:
                version_id = uuid.UUID(node.config["version_id"])
            except (KeyError, ValueError, TypeError):
                fail(422, "AGENT_VERSION_UNAVAILABLE", "Select an executable agent version.")
            version = db.scalar(select(AgentVersion).where(
                AgentVersion.id == version_id, AgentVersion.workspace_id == workspace_id,
                AgentVersion.purpose == "published",
            ))
            connection = db.scalar(select(IntegrationConnection).where(
                IntegrationConnection.id == version.connection_id,
                IntegrationConnection.workspace_id == workspace_id,
            )) if version else None
            secret = db.scalar(select(SecretReference).where(
                SecretReference.connection_id == version.connection_id,
                SecretReference.generation == version.credential_generation,
            )) if version else None
            if not version or not connection or connection.state != "active" or connection.credential_generation != version.credential_generation or not secret or version.config["model_id"] not in connection.verified_models:
                fail(409, "AGENT_VERSION_UNAVAILABLE", "This agent version or credential is no longer available.")
            config = version.config
            installed = set(db.scalars(select(ToolInstallation.tool_key).where(ToolInstallation.workspace_id == workspace_id)))
            if set(config.get("tool_keys", [])) - installed:
                fail(409, "TOOL_APPROVAL_REVOKED", "An agent tool is no longer approved in this workspace.")
            model = (config.get("provider", "openai"), config.get("model_id"))
            if model not in MODEL_PRICES:
                fail(422, "RUNTIME_UNSUPPORTED", "This agent model cannot run in a workflow.")
            from app.providers.profiles import capability
            if config.get("tool_keys") and not capability(*model).local_tools:
                fail(422, "RUNTIME_UNSUPPORTED", "This model does not support local tools.")
            if example_errors(config["input_schema"], data, "input"):
                fail(422, "AGENT_INPUT_SCHEMA_INVALID", "Workflow data does not match the agent input schema.")
            input_text = _canonical(data)
            estimated_bytes = len((config["instructions"] + input_text + _canonical(config["output_schema"])).encode()) + 4096
            if estimated_bytes > MAX_INPUT_BYTES:
                fail(422, "INPUT_TOO_LARGE", "Agent step input is too large.")
            input_price, output_price = MODEL_PRICES[model]
            budget = min(Decimal(graph.limits["max_cost_usd"]), Decimal(config["limits"]["max_cost_usd"]))
            input_reserve = input_price * estimated_bytes
            max_output = min(MAX_OUTPUT_TOKENS, config["limits"].get("max_output_tokens", 4096), int((budget - input_reserve) / output_price))
            if max_output < 16:
                fail(422, "BUDGET_TOO_SMALL", "The workflow budget cannot cover this agent step.")
            key = decrypt_secret(master, workspace_id, connection.id, secret.generation, secret.nonce, secret.ciphertext)
            timeout = min(25.0, float(config["limits"]["timeout_seconds"]), (run.deadline_at - now).total_seconds())
            if timeout < 1:
                fail(408, "RUN_TIMEOUT", "This workflow run timed out.")
            run.external_started_at = now
            db.commit()
        if config.get("tool_keys"):
            output, input_tokens, output_tokens = generate_openai_with_tools(
                key, version, data, max_output, timeout, settings,
                active_check=active, budget_override=budget,
            )
        else:
            output, input_tokens, output_tokens = generate(key, version, data, max_output, timeout)
        cost = input_price * input_tokens + output_price * output_tokens
        with sessions() as db:
            run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == identity).with_for_update())
            if run and run.state == "running" and run.claim_token == token:
                run.input_tokens = input_tokens
                run.output_tokens = output_tokens
                run.cost_usd = cost
                db.commit()
        return output, {
            "agent_version_id": str(version.id), "tool_keys": config.get("tool_keys", []), "input_tokens": input_tokens,
            "output_tokens": output_tokens, "cost_usd": str(cost),
        }
    return call


def _mcp_handler(sessions, identity, token, workspace_id, master, settings):
    def call(node, data):
        with sessions() as db:
            run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == identity).with_for_update())
            now = datetime.now(UTC)
            if not run or run.state != "running" or run.claim_token != token or run.cancel_requested_at:
                fail(409, "RUN_INTERRUPTED", "This workflow run was interrupted.")
            if now >= run.deadline_at:
                fail(408, "RUN_TIMEOUT", "This workflow run timed out.")
            server_id, tool_name = node.config["server_id"], node.config["tool_name"]
            profile = catalog(settings.mcp_catalog_json).get(server_id)
            connection = db.scalar(select(McpConnection).where(
                McpConnection.workspace_id == workspace_id, McpConnection.server_id == server_id,
            ))
            snapshot = next((item for item in connection.tool_snapshots if item["name"] == tool_name), None) if connection and connection.state == "active" else None
            if not profile or tool_name not in profile.get("read_only_tools", []) or not connection or connection.state != "active" or tool_name not in connection.verified_tools or not snapshot or connection.generation != node.config.get("connection_generation") or schema_hash(snapshot["input_schema"]) != node.config.get("input_schema_hash"):
                fail(409, "MCP_GRANT_CHANGED", "The MCP connection or tool schema changed. Republish the workflow.")
            if example_errors(snapshot["input_schema"], data, "input"):
                fail(422, "MCP_INPUT_SCHEMA_INVALID", "Workflow data does not match the MCP tool input schema.")
            key = decrypt_secret(master, workspace_id, connection.id, connection.generation, connection.nonce, connection.ciphertext) if connection.nonce and connection.ciphertext else ""
            run.external_started_at = now
            db.commit()
        output = call_tool(profile["url"], key, tool_name, data)
        if output.get("isError"):
            fail(502, "MCP_TOOL_FAILED", "The MCP tool reported an error.")
        return output
    return call


def execute(run_id: str, settings=None) -> None:
    from app.core.config import Settings
    from app.core.db import make_sessions

    settings = settings or Settings()
    sessions = make_sessions(settings.database_url)
    master = load_master_key(settings.credential_key_path)
    identity = uuid.UUID(run_id)
    token = uuid.uuid4()
    try:
        with sessions() as db:
            run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == identity).with_for_update())
            if not run or run.state != "queued":
                return
            now = datetime.now(UTC)
            if run.cancel_requested_at or now >= run.deadline_at:
                run.state = "cancelled" if run.cancel_requested_at else "failed"
                run.error_code = None if run.cancel_requested_at else "RUN_TIMEOUT"
                run.finished_at = now
                db.commit()
                return
            version = db.scalar(
                select(WorkflowVersion).where(
                    WorkflowVersion.id == run.version_id,
                    WorkflowVersion.workspace_id == run.workspace_id,
                )
            )
            input_data = json.loads(
                decrypt_secret(
                    master, run.workspace_id, run.id, 1, run.input_nonce, run.input_ciphertext
                )
            )
            workspace_id = run.workspace_id
            graph_data = deepcopy(version.graph)
            run.state = "running"
            run.started_at = now
            run.claim_token = token
            db.commit()
        graph = Graph.model_validate(graph_data)
        has_agent = any(node.type == "agent" for node in graph.nodes)
        has_mcp = any(node.type == "mcp_tool" for node in graph.nodes)
        try:
            with sessions() as db:
                result = run_preview(
                    db, workspace_id, graph, input_data,
                    agent_handler=_agent_handler(sessions, identity, token, workspace_id, master, graph, settings) if has_agent else None,
                    mcp_handler=_mcp_handler(sessions, identity, token, workspace_id, master, settings) if has_mcp else None,
                    mcp_catalog_json=settings.mcp_catalog_json,
                    max_seconds=30 if has_agent or has_mcp else 5,
                )
            error_code = None
        except ProviderFailure as error:
            result = None
            error_code = error.code
        except HTTPException as error:
            result = None
            error_code = (
                error.detail.get("code", "WORKFLOW_FAILED")
                if isinstance(error.detail, dict)
                else "WORKFLOW_FAILED"
            )
        except Exception:
            result = None
            error_code = "WORKFLOW_FAILED"
        with sessions() as db:
            run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == identity).with_for_update())
            if not run or run.state != "running" or run.claim_token != token:
                return
            now = datetime.now(UTC)
            run.finished_at = now
            if run.cancel_requested_at:
                run.state = "cancelled"
                if has_agent and run.external_started_at and run.cost_usd is None:
                    run.uncertain_cost_usd = Decimal(graph.limits["max_cost_usd"])
            elif now >= run.deadline_at:
                run.state, run.error_code = "failed", "RUN_TIMEOUT"
                if has_agent and run.external_started_at and run.cost_usd is None:
                    run.uncertain_cost_usd = Decimal(graph.limits["max_cost_usd"])
            elif error_code:
                run.state, run.error_code = "failed", error_code
                if has_agent and run.external_started_at and run.cost_usd is None:
                    run.uncertain_cost_usd = Decimal(graph.limits["max_cost_usd"])
            else:
                agent_step = next((step for step in result["steps"] if step["type"] == "agent"), None)
                if agent_step:
                    usage = agent_step["usage"]
                    run.input_tokens = usage["input_tokens"]
                    run.output_tokens = usage["output_tokens"]
                    run.cost_usd = Decimal(usage["cost_usd"])
                run.output_nonce, run.output_ciphertext = encrypt_secret(
                    master, run.workspace_id, run.id, 2, _canonical(result)
                )
                run.state = "completed"
            db.commit()
    finally:
        sessions.kw["bind"].dispose()
