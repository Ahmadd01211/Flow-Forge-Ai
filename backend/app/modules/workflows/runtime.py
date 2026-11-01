"""Durable bounded DAG execution with checkpointed local, agent, MCP and HTTP steps."""

import hashlib
import json
import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from app.core.credentials import decrypt_secret, encrypt_secret, load_master_key
from app.core.errors import fail
from app.core.json_contracts import bounded_json, example_errors
from app.modules.agents.models import AgentVersion
from app.modules.audit.service import record
from app.modules.executions.authorization import assert_authorized
from app.modules.executions.runtime import (
    ProviderFailure,
    checked_usage,
    generate,
    generate_openai_with_tools,
)
from app.modules.executions.service import MAX_INPUT_BYTES, MAX_OUTPUT_TOKENS, MODEL_PRICES
from app.modules.integrations.models import IntegrationConnection, SecretReference
from app.modules.mcp import registry
from app.modules.mcp.client import call_tool
from app.modules.mcp.models import McpConnection
from app.modules.mcp.service import schema_hash
from app.modules.tools.models import ToolInstallation
from app.modules.workflows.checkpoints import Checkpoints, settle_unfinished
from app.modules.workflows.checkpoints import rows as checkpoint_rows
from app.modules.workflows.checkpoints import view as checkpoint_view
from app.modules.workflows.models import Workflow, WorkflowRun, WorkflowVersion
from app.modules.workflows.pauses import Parked
from app.modules.workflows.preview import validation
from app.modules.workflows.schemas import Graph
from app.modules.workspaces.models import Workspace


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _executable(db: Session, workspace_id: uuid.UUID, graph: Graph, mcp_catalog_json: str = "[]", root_workflow_id=None) -> dict:
    try:
        budget = Decimal(graph.limits["max_cost_usd"])
    except (KeyError, TypeError, ValueError, ArithmeticError):
        fail(422, "WORKFLOW_BUDGET_INVALID", "Set a valid workflow budget.")
    if not budget.is_finite() or budget <= 0 or budget > 10:
        fail(422, "WORKFLOW_BUDGET_INVALID", "Set a workflow budget between $0 and $10.")
    checked = validation(db, workspace_id, graph, mcp_catalog_json, root_workflow_id=root_workflow_id)
    if not checked["valid"]:
        fail(422, "WORKFLOW_INVALID", checked["errors"][0]["message"])
    if not checked["publishable"]:
        fail(
            422,
            "RUNTIME_UNSUPPORTED",
            "This workflow shape is not yet supported for published runs.",
        )
    return checked


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
    _executable(db, workspace_id, graph, mcp_catalog_json, root_workflow_id=row.id)
    for node in graph.nodes:
        if node.type in {"subworkflow", "for_each"}:
            from app.modules.workflows.composition import resolve_version
            child, _ = resolve_version(db, workspace_id, {"version_id": node.config["version_id"]})
            node.config = {**node.config, "graph_hash": child.graph_hash}
        if node.type == "http_tool":
            from app.modules.http_tools.service import resolve
            tool = resolve(db, workspace_id, node.config, pinned=False)
            node.config = {"tool_id": str(tool.id), "connection_generation": tool.generation, "spec_hash": tool.spec_hash}
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
    automation_id: uuid.UUID | None = None,
    commit: bool = True,
) -> tuple[WorkflowRun, bool]:
    if not 8 <= len(idempotency_key) <= 128 or any(ch.isspace() for ch in idempotency_key):
        fail(
            422, "IDEMPOTENCY_KEY_INVALID", "Use an 8–128 character idempotency key without spaces."
        )
    bounded_json(input_data, max_bytes=65536)
    db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    scope = f"automation:{automation_id}:" if automation_id else f"{deployment_id}:" if deployment_id else ""
    key_hash = hashlib.sha256((scope + idempotency_key).encode()).hexdigest()
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
    checked = _executable(db, workspace_id, graph, mcp_catalog_json, root_workflow_id=version.workflow_id)
    if example_errors(graph.input_schema, input_data, "input"):
        fail(422, "INPUT_SCHEMA_INVALID", "Input does not match this workflow version.")
    count = (
        db.scalar(
            select(func.count())
            .select_from(WorkflowRun)
            .where(
                WorkflowRun.workspace_id == workspace_id,
                WorkflowRun.state.in_(["queued", "running", "waiting"]),
            )
        )
        or 0
    )
    if count >= 2:
        fail(429, "RUN_CONCURRENCY_LIMIT", "This workspace already has two active workflow runs.")
    from app.modules.workspaces.usage import admit
    reserved = Decimal(graph.limits["max_cost_usd"]) if checked["agent_steps"] else Decimal("0")
    admit(db, workspace_id, reserved)
    run_id = uuid.uuid4()
    nonce, ciphertext = encrypt_secret(master, workspace_id, run_id, 1, _canonical(input_data))
    run = WorkflowRun(
        id=run_id,
        workspace_id=workspace_id,
        version_id=version_id,
        deployment_id=deployment_id,
        automation_id=automation_id,
        requested_by=actor_id,
        idempotency_key_hash=key_hash,
        request_hash=request_hash,
        state="queued",
        reserved_max_usd=reserved,
        input_nonce=nonce,
        input_ciphertext=ciphertext,
        deadline_at=datetime.now(UTC) + timedelta(seconds=min(graph.limits.get("timeout_seconds", 60), 30 if checked["has_external"] else 15)),
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
    if commit:
        db.commit()
    else:
        db.flush()
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


def public_run(run: WorkflowRun, master: bytes, detail: bool = True) -> dict:
    from app.modules.workflows.models import WorkflowPause
    from app.modules.workflows.pauses import public_pause
    result = (
        json.loads(
            decrypt_secret(
                master, run.workspace_id, run.id, 2, run.output_nonce, run.output_ciphertext
            )
        )
        if detail and run.output_nonce and run.output_ciphertext
        else None
    )
    db = object_session(run)
    progress = checkpoint_rows(db, run.workspace_id, run.id) if detail and db is not None else []
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "version_id": run.version_id,
        "automation_id": run.automation_id,
        "deployment_id": run.deployment_id,
        "state": run.state,
        "requested_by": run.requested_by,
        "pauses": [public_pause(row) for row in db.scalars(select(WorkflowPause).where(WorkflowPause.workspace_id == run.workspace_id, WorkflowPause.run_id == run.id).order_by(WorkflowPause.created_at, WorkflowPause.id)).all()] if detail and db is not None else [],
        "output": result["output"] if result else None,
        "steps": [checkpoint_view(row, master) for row in progress] if progress else result["steps"] if result else None,
        "error_code": run.error_code,
        "cost_usd": str(run.cost_usd) if run.cost_usd is not None else None,
        "reserved_max_usd": str(run.reserved_max_usd),
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
    if run.state in {"queued", "waiting"}:
        if run.state == "waiting":
            from app.modules.workflows.pauses import pending, stop
            pause = pending(db, run)
            if pause:
                stop(db, run, pause, "cancelled", None, actor_id)
        run.state = "cancelled"
        run.finished_at = run.cancel_requested_at
        settle_unfinished(db, run, "RUN_CANCELLED")
    record(
        db, workspace_id, actor_id, "workflow_run.cancel_requested", run.id, {"state": run.state}
    )
    db.commit()
    return run


def _agent_handler(sessions, identity, token, workspace_id, master, graph, settings):
    def active() -> bool:
        with sessions() as db:
            current = db.scalar(select(WorkflowRun).where(WorkflowRun.id == identity))
            if current:
                try:
                    assert_authorized(db, current)
                except HTTPException:
                    return False
            return bool(current and current.state == "running" and current.claim_token == token and not current.cancel_requested_at and datetime.now(UTC) < current.deadline_at)

    def call(node, data):
        with sessions() as db:
            run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == identity).with_for_update())
            if not run or run.state != "running" or run.claim_token != token or run.cancel_requested_at:
                fail(409, "RUN_INTERRUPTED", "This workflow run was interrupted.")
            now = datetime.now(UTC)
            if now >= run.deadline_at:
                fail(408, "RUN_TIMEOUT", "This workflow run timed out.")
            assert_authorized(db, run)
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
            from app.modules.agents.tool_grants import validate_grants
            validate_grants(db, workspace_id, config, settings.mcp_catalog_json)
            installed = set(db.scalars(select(ToolInstallation.tool_key).where(ToolInstallation.workspace_id == workspace_id)))
            if set(config.get("tool_keys", [])) - installed:
                fail(409, "TOOL_APPROVAL_REVOKED", "An agent tool is no longer approved in this workspace.")
            model = (config.get("provider", "openai"), config.get("model_id"))
            if model not in MODEL_PRICES:
                fail(422, "RUNTIME_UNSUPPORTED", "This agent model cannot run in a workflow.")
            from app.providers.profiles import capability
            if (config.get("tool_keys") or config.get("mcp_tools") or config.get("http_tools")) and not capability(*model).local_tools:
                fail(422, "RUNTIME_UNSUPPORTED", "This model does not support local tools.")
            if example_errors(config["input_schema"], data, "input"):
                fail(422, "AGENT_INPUT_SCHEMA_INVALID", "Workflow data does not match the agent input schema.")
            input_text = _canonical(data)
            estimated_bytes = len((config["instructions"] + input_text + _canonical(config["output_schema"])).encode()) + 4096
            if estimated_bytes > MAX_INPUT_BYTES:
                fail(422, "INPUT_TOO_LARGE", "Agent step input is too large.")
            input_price, output_price = MODEL_PRICES[model]
            remaining_budget = Decimal(graph.limits["max_cost_usd"]) - (run.cost_usd or Decimal("0"))
            budget = min(remaining_budget, Decimal(config["limits"]["max_cost_usd"]))
            input_reserve = input_price * estimated_bytes
            max_output = min(MAX_OUTPUT_TOKENS, config["limits"].get("max_output_tokens", 4096), int((budget - input_reserve) / output_price))
            if max_output < 16:
                fail(422, "BUDGET_TOO_SMALL", "The workflow budget cannot cover this agent step.")
            key = decrypt_secret(master, workspace_id, connection.id, secret.generation, secret.nonce, secret.ciphertext)
            timeout = min(25.0, float(config["limits"]["timeout_seconds"]), float(node.policy.get("timeout_seconds", 60)), (run.deadline_at - now).total_seconds())
            if timeout < 1:
                fail(408, "RUN_TIMEOUT", "This workflow run timed out.")
            run.external_started_at = now
            run.external_inflight = True
            run.heartbeat_at = now
            # Hold a possible-charge estimate before this call. If the process
            # dies after an earlier agent succeeded, both amounts survive.
            run.uncertain_cost_usd = budget
            db.commit()
        if config.get("tool_keys") or config.get("mcp_tools") or config.get("http_tools"):
            output, input_tokens, output_tokens = generate_openai_with_tools(
                key, version, data, max_output, timeout, settings,
                active_check=active, budget_override=budget,
            )
        else:
            output, input_tokens, output_tokens = generate(key, version, data, max_output, timeout)
        input_tokens, output_tokens = checked_usage(input_tokens, output_tokens)
        cost = input_price * input_tokens + output_price * output_tokens
        with sessions() as db:
            run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == identity).with_for_update())
            if run and run.state == "running" and run.claim_token == token:
                run.input_tokens = (run.input_tokens or 0) + input_tokens
                run.output_tokens = (run.output_tokens or 0) + output_tokens
                run.cost_usd = (run.cost_usd or Decimal("0")) + cost
                run.uncertain_cost_usd = None
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
            assert_authorized(db, run)
            server_id, tool_name = node.config["server_id"], node.config["tool_name"]
            profile = registry.server(db, workspace_id, server_id, settings.mcp_catalog_json)
            connection = db.scalar(select(McpConnection).where(
                McpConnection.workspace_id == workspace_id, McpConnection.server_id == server_id,
            ))
            snapshot = registry.snapshot(connection, tool_name)
            if not registry.runnable(profile, connection, tool_name) or connection.generation != node.config.get("connection_generation") or schema_hash(snapshot["input_schema"]) != node.config.get("input_schema_hash"):
                fail(409, "MCP_GRANT_CHANGED", "The MCP connection or tool schema changed. Republish the workflow.")
            if example_errors(snapshot["input_schema"], data, "input"):
                fail(422, "MCP_INPUT_SCHEMA_INVALID", "Workflow data does not match the MCP tool input schema.")
            url, key = registry.endpoint(profile, connection, master)
            run.external_started_at = now
            run.external_inflight = True
            run.heartbeat_at = now
            remaining_timeout = min(12.0, float(node.policy.get("timeout_seconds", 60)), (run.deadline_at - now).total_seconds())
            db.commit()
        output = call_tool(url, key, tool_name, data, remaining_timeout)
        if output.get("isError"):
            fail(502, "MCP_TOOL_FAILED", "The MCP tool reported an error.")
        return output
    return call


def _http_handler(sessions, identity, token, workspace_id, settings):
    from app.modules.http_tools import service

    def call(node, data):
        with sessions() as db:
            run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == identity).with_for_update())
            now = datetime.now(UTC)
            if not run or run.state != "running" or run.claim_token != token or run.cancel_requested_at:
                fail(409, "RUN_INTERRUPTED", "This workflow run was interrupted.")
            if now >= run.deadline_at:
                fail(408, "RUN_TIMEOUT", "This workflow run timed out.")
            assert_authorized(db, run)
            row = service.resolve(db, workspace_id, node.config)
            if not isinstance(data, dict) or example_errors(row.spec["input_schema"], data, "input"):
                fail(422, "HTTP_INPUT_SCHEMA_INVALID", "Input does not match this HTTP tool's contract.")
            timeout = min(12.0, float(node.policy.get("timeout_seconds", 60)), (run.deadline_at - now).total_seconds())
            run.external_started_at = now
            run.external_inflight = True
            run.heartbeat_at = now
            db.commit()
            return service.invoke(db, workspace_id, node.config, data, settings, timeout=timeout)
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
            if run.external_inflight or (run.heartbeat_at is None and run.external_started_at is not None):
                run.state, run.error_code, run.finished_at = "failed", "EXTERNAL_OUTCOME_UNKNOWN", now
                if run.cost_usd is None and run.uncertain_cost_usd is None and run.reserved_max_usd > 0:
                    run.uncertain_cost_usd = run.reserved_max_usd
                settle_unfinished(db, run, run.error_code)
                db.commit()
                return
            if run.cancel_requested_at or now >= run.deadline_at:
                run.state = "cancelled" if run.cancel_requested_at else "failed"
                run.error_code = None if run.cancel_requested_at else "RUN_TIMEOUT"
                run.finished_at = now
                settle_unfinished(db, run, run.error_code or "RUN_CANCELLED")
                db.commit()
                return
            version = db.scalar(
                select(WorkflowVersion).where(
                    WorkflowVersion.id == run.version_id,
                    WorkflowVersion.workspace_id == run.workspace_id,
                )
            )
            try:
                assert_authorized(db, run)
            except HTTPException:
                run.state, run.error_code, run.finished_at = "failed", "RUN_AUTHORIZATION_REVOKED", now
                settle_unfinished(db, run, run.error_code)
                db.commit()
                return
            input_data = json.loads(
                decrypt_secret(
                    master, run.workspace_id, run.id, 1, run.input_nonce, run.input_ciphertext
                )
            )
            workspace_id = run.workspace_id
            root_workflow_id, deadline_at = version.workflow_id, run.deadline_at
            graph_data = deepcopy(version.graph)
            run.state = "running"
            run.started_at = run.started_at or now
            run.heartbeat_at = now
            run.claim_token = token
            db.commit()
        graph = Graph.model_validate(graph_data)
        try:
            with sessions() as db:
                checked = _executable(db, workspace_id, graph, settings.mcp_catalog_json, root_workflow_id=root_workflow_id)
            from app.modules.workflows.runner import DurableRunner
            runner = DurableRunner(sessions, identity, token, workspace_id, master, settings)
            deadline = min(deadline_at, datetime.now(UTC) + timedelta(seconds=30 if checked["has_external"] else 15))
            result = runner.run(graph, input_data, Checkpoints(sessions, workspace_id, identity, token, master), deadline, Decimal(graph.limits["max_cost_usd"]), (root_workflow_id,))
            error_code = None
        except Parked:
            return
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
            elif now >= run.deadline_at:
                run.state, run.error_code = "failed", "RUN_TIMEOUT"
            elif error_code:
                run.state, run.error_code = "failed", error_code
            else:
                run.output_nonce, run.output_ciphertext = encrypt_secret(
                    master, run.workspace_id, run.id, 2, _canonical(result)
                )
                run.state = "completed"
            settle_unfinished(db, run, run.error_code or ("RUN_CANCELLED" if run.state == "cancelled" else "WORKFLOW_FAILED"))
            db.commit()
    finally:
        sessions.kw["bind"].dispose()
