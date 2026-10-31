"""Run one draft node on sample input.

Local steps run inline with the same code as preview and published runs. Steps that leave the
platform require explicit confirmation: MCP/HTTP reads share their service test limits,
agents become budgeted agent runs, and HTTP writes require a published workflow receipt.
"""

import time
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.credentials import load_master_key
from app.core.errors import fail
from app.core.json_contracts import bounded_json
from app.modules.audit.service import record
from app.modules.executions import service as executions
from app.modules.executions.schemas import RunCreate
from app.modules.mcp import service as mcp
from app.modules.workflows.preview import run_step, validation
from app.modules.workflows.schemas import Graph

EXTERNAL_NODES = {"agent", "mcp_tool", "http_tool"}


def run_node_test(
    db: Session,
    workspace_id: uuid.UUID,
    workflow_id: uuid.UUID,
    actor_id: uuid.UUID,
    graph: Graph,
    node_id: str,
    input_data: object,
    outputs: dict,
    confirm_external: bool,
    idempotency_key: str | None,
    settings,
    redis,
) -> dict:
    node = next((item for item in graph.nodes if item.id == node_id), None)
    if not node:
        fail(404, "NODE_NOT_FOUND", "This step is not in the workflow draft.")
    bounded_json(input_data, max_bytes=65536)
    bounded_json(outputs, max_bytes=262144)
    # Only this node's own settings block a test; an unfinished graph around it does not.
    blocking = [
        error for error in validation(db, workspace_id, graph, settings.mcp_catalog_json, root_workflow_id=workflow_id)["errors"]
        if error["node_id"] == node.id and (error["path"] or "").startswith(("config", "policy."))
    ]
    if blocking:
        fail(422, "NODE_CONFIG_INVALID", blocking[0]["message"])
    external = node.type in EXTERNAL_NODES
    if external and not confirm_external:
        fail(422, "EXTERNAL_TEST_UNCONFIRMED", "Confirm this test first: it calls a service outside FlowForge.")
    if external and not isinstance(input_data, dict):
        fail(422, "NODE_TEST_INPUT_INVALID", "This step needs a JSON object as input.")
    result = {
        "node_id": node.id, "type": node.type, "status": "completed", "output": None,
        "selected_port": None, "error": None, "duration_ms": 0, "external": external, "agent_run": None,
    }
    if node.type == "agent":
        if not idempotency_key:
            fail(422, "IDEMPOTENCY_KEY_REQUIRED", "Agent tests need an Idempotency-Key header.")
        master = load_master_key(settings.credential_key_path)
        run, _ = executions.submit(
            db, workspace_id, actor_id,
            RunCreate(version_id=uuid.UUID(node.config["version_id"]), input=input_data),
            idempotency_key, master, raw_catalog=settings.mcp_catalog_json,
        )
        return {**result, "status": "queued", "agent_run": executions.public_run(run, master)}
    started = time.monotonic()
    try:
        if node.type in {"subworkflow", "for_each"}:
            from app.modules.workflows.composition import preview_handler, resolve_version
            child_version, child = resolve_version(db, workspace_id, node.config)
            checked = validation(db, workspace_id, child, settings.mcp_catalog_json, root_workflow_id=child_version.workflow_id)
            if checked["has_external"] or checked["has_pause"]:
                fail(422, "SUBWORKFLOW_TEST_REQUIRES_RUN", "Publish and run this workflow to execute nested external steps with durable receipts and budgets.")
            handler = preview_handler(db, workspace_id, settings.mcp_catalog_json, time.monotonic() + 5, (workflow_id,))
            step = run_step(node, input_data, outputs, composition_handler=handler)
        elif node.type == "http_tool":
            from app.modules.http_tools import service as http
            row = http.resolve(db, workspace_id, node.config, pinned=False)
            if row.spec["method"] != "GET" or not row.spec["read_only"]:
                fail(422, "HTTP_TEST_REQUIRES_WORKFLOW", "Run write actions through a published workflow to retain receipts and failure evidence.")
            grant = {"tool_id": str(row.id), "connection_generation": row.generation, "spec_hash": row.spec_hash}
            http.check_test_rate(redis, workspace_id)
            record(db, workspace_id, actor_id, "http_tool.tested", row.id, {"generation": row.generation})
            db.commit()
            step = {"output": http.invoke(db, workspace_id, grant, input_data, settings, timeout=min(12, node.policy.get("timeout_seconds", 60)))}
        elif node.type == "mcp_tool":
            mcp.check_test_rate(redis, workspace_id)
            record(db, workspace_id, actor_id, "workflow.node_tested", workflow_id, {
                "node_id": node.id, "server_id": node.config["server_id"], "tool_name": node.config["tool_name"],
            })
            db.commit()
            step = {"output": mcp.test_tool(
                db, workspace_id, settings.mcp_catalog_json, settings.credential_key_path,
                node.config["server_id"], node.config["tool_name"], input_data,
            )["output"]}
            bounded_json(step["output"], max_bytes=65536)
        else:
            step = run_step(node, input_data, outputs)
    except HTTPException as error:
        if error.status_code == 429:
            raise
        detail = error.detail if isinstance(error.detail, dict) else {}
        return {
            **result, "status": "failed", "duration_ms": round((time.monotonic() - started) * 1000),
            "error": {"code": detail.get("code", "NODE_TEST_FAILED"), "message": detail.get("message", "This step failed.")},
        }
    return {
        **result, "output": step["output"], "selected_port": step.get("selected_port"),
        "duration_ms": round((time.monotonic() - started) * 1000),
    }
