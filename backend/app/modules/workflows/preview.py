"""Deterministic bounded DAG execution for preview and durable workflow workers."""

import json
import re
import time
import uuid
from copy import deepcopy
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import fail
from app.core.json_contracts import bounded_json, example_errors, json_equality_key
from app.modules.agents.models import AgentVersion
from app.modules.executions.service import MODEL_PRICES
from app.modules.integrations.models import IntegrationConnection
from app.modules.mcp import registry
from app.modules.mcp.models import McpConnection
from app.modules.mcp.service import schema_hash
from app.modules.tools.catalog import CATALOG, invoke
from app.modules.tools.models import ToolInstallation
from app.modules.workflows.composition import (
    COMPOSITE_NODES,
    MAX_AGENT_STEPS,
    MAX_CALL_DEPTH,
    MAX_EXPANDED_STEPS,
    resolve_version,
)
from app.modules.workflows.domain import validate_graph
from app.modules.workflows.node_config import config_issues
from app.modules.workflows.pauses import MAX_PAUSE_SECONDS, PAUSE_NODES, Parked
from app.modules.workflows.schemas import Graph


def _safe_pointer(path: object) -> bool:
    return isinstance(path, str) and len(path) <= 512 and (not path or path.startswith("/")) and all(
        part.replace("~1", "/").replace("~0", "~") not in {"__proto__", "constructor", "prototype"}
        for part in path.split("/")[1:]
    )


ENTRY_NODES = {"manual_input", "webhook_trigger", "schedule_trigger", "chat_trigger"}
LOCAL_NODES = ENTRY_NODES | {"tool", "transform", "condition", "switch", "merge", "text_template", "list_filter", "list_deduplicate", "json_parse", "result"}
# An inline LLM step is published as a hidden agent version, so it runs and counts as an agent.
AGENT_NODES = {"agent", "llm"}
EXTERNAL_NODES = AGENT_NODES | {"mcp_tool", "http_tool"}


def _always_before(graph: Graph, node_id: str, upstream: set[str]) -> set[str]:
    """Upstream steps on every path from the trigger, found by removing each in turn."""
    entry = next((node.id for node in graph.nodes if node.type in ENTRY_NODES), None)
    outgoing: dict[str, list[str]] = {}
    for edge in graph.edges:
        outgoing.setdefault(edge.source, []).append(edge.target)

    def reaches(blocked: str) -> bool:
        found, pending = set(), [entry]
        while pending:
            key = pending.pop()
            if key == node_id:
                return True
            if key in found or key == blocked:
                continue
            found.add(key)
            pending.extend(outgoing.get(key, []))
        return False

    return {step for step in upstream if step == entry or not reaches(step)} if entry else set()


def _upstream(graph: Graph, node_id: str) -> set[str]:
    incoming: dict[str, list[str]] = {}
    for edge in graph.edges:
        incoming.setdefault(edge.target, []).append(edge.source)
    found: set[str] = set()
    pending = list(incoming.get(node_id, []))
    while pending:
        key = pending.pop()
        if key not in found:
            found.add(key)
            pending.extend(incoming.get(key, []))
    return found


def _compare(left: object, right: object, operator: str) -> bool:
    if operator == "exists":
        return left is not None
    if operator == "eq":
        return left == right
    if operator == "ne":
        return left != right
    if operator == "contains":
        return (isinstance(left, str) and isinstance(right, str) and right in left) or (isinstance(left, list) and right in left) or (isinstance(left, dict) and isinstance(right, str) and right in left)
    if type(left) not in (str, int, float) or type(left) is not type(right):
        fail(422, "COMPARISON_INVALID", "Comparison values must have matching number or text types.")
    return {"gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right}[operator]


def _value(reference: dict, data: object) -> object:
    return reference["value"] if reference["kind"] == "literal" else _pointer(data, reference["pointer"])


def _canonical_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validation(db: Session, workspace_id: uuid.UUID, graph: Graph, mcp_catalog_json: str = "[]", *, root_workflow_id=None, _ancestry=(), _depth=0, _context=None) -> dict:
    result = validate_graph(graph)
    context = _context if _context is not None else {"versions": {}, "checks": {}, "inspected_nodes": 0}
    ancestry = (*_ancestry, root_workflow_id) if root_workflow_id else _ancestry
    result.update(expanded_steps=len(graph.nodes), agent_steps=sum(node.type in AGENT_NODES for node in graph.nodes), has_external=any(node.type in EXTERNAL_NODES for node in graph.nodes), has_pause=any(node.type in PAUSE_NODES for node in graph.nodes), pause_seconds=0)
    context["inspected_nodes"] += len(graph.nodes)
    if context["inspected_nodes"] > 400:
        result["errors"].append({"code": "SUBWORKFLOW_DEPENDENCY_LIMIT", "message": "This dependency tree is too large to inspect. Reduce the number of reusable workflows.", "node_id": None, "edge_id": None, "path": None})
        result.update(valid=False, publishable=False)
        return result
    timeout = graph.limits.get("timeout_seconds", 60)
    if type(timeout) is not int or not 1 <= timeout <= 300:
        result["errors"].append({"code": "WORKFLOW_TIMEOUT_INVALID", "message": "Workflow timeout must be a whole number from 1 to 300 seconds.", "node_id": None, "edge_id": None, "path": "limits.timeout_seconds"})
    try:
        budget = Decimal(graph.limits["max_cost_usd"])
    except (KeyError, TypeError, ValueError, InvalidOperation):
        budget = Decimal(0)
    if not budget.is_finite() or budget <= 0 or budget > 10:
        result["errors"].append({
            "code": "WORKFLOW_BUDGET_INVALID", "message": "Set a workflow budget above $0 and no more than $10.",
            "node_id": None, "edge_id": None, "path": "limits.max_cost_usd",
        })
    installed = set(
        db.scalars(
            select(ToolInstallation.tool_key).where(ToolInstallation.workspace_id == workspace_id)
        )
    )
    approved_servers = registry.servers(db, workspace_id, mcp_catalog_json)
    from app.modules.workflows.chat import CHAT_SAMPLE
    for node in graph.nodes:
        if node.type == "chat_trigger" and example_errors(graph.input_schema, CHAT_SAMPLE, "input"):
            result["errors"].append({"code": "CHAT_INPUT_INCOMPATIBLE", "message": "A chat trigger sends conversation_id and message. Make the workflow input schema accept them.", "node_id": node.id, "edge_id": None, "path": "input_schema"})
        upstream = _upstream(graph, node.id) if node.type == "result" else None
        config_errors, config_warnings = config_issues(
            node, upstream, _always_before(graph, node.id, upstream) if upstream is not None else None
        )
        result["errors"].extend(config_errors)
        result["warnings"].extend(config_warnings)
        if config_errors:
            continue
        if node.type in PAUSE_NODES:
            result["pause_seconds"] += node.config["seconds"] if node.type == "wait" else node.config["expires_seconds"]
            continue
        if node.type in COMPOSITE_NODES:
            try:
                version, child = resolve_version(db, workspace_id, node.config, context["versions"])
                if version.workflow_id in ancestry:
                    fail(422, "SUBWORKFLOW_RECURSION", "A workflow cannot call itself or an ancestor, including older versions.")
                if _depth + 1 >= MAX_CALL_DEPTH:
                    fail(422, "SUBWORKFLOW_DEPTH_LIMIT", "Use at most three workflow levels including the parent.")
                key = (version.id, ancestry)
                if key not in context["checks"]:
                    context["checks"][key] = validation(db, workspace_id, child, mcp_catalog_json, _ancestry=(*ancestry, version.workflow_id), _depth=_depth + 1, _context=context)
                checked = context["checks"][key]
                # Preserve effects even when a dependency is temporarily invalid.
                # Replay consent must not disappear when an approval is revoked
                # and then restored between preflight and admission.
                result["has_external"] |= checked["has_external"]
                result["has_pause"] |= checked["has_pause"]
                if not checked["publishable"]:
                    message = checked["errors"][0]["message"] if checked["errors"] else "The child exceeds the supported runtime limits."
                    fail(422, "SUBWORKFLOW_INVALID", "Child workflow: " + message)
                multiplier = node.config["max_items"] if node.type == "for_each" else 1
                result["expanded_steps"] += checked["expanded_steps"] * multiplier
                result["agent_steps"] += checked["agent_steps"] * multiplier
                result["pause_seconds"] += checked["pause_seconds"] * multiplier
            except HTTPException as error:
                detail = error.detail if isinstance(error.detail, dict) else {}
                result["has_external"] = True
                result["errors"].append({"code": detail.get("code", "SUBWORKFLOW_INVALID"), "message": detail.get("message", "Review this workflow dependency."), "node_id": node.id, "edge_id": None, "path": "config.version_id"})
            continue
        if node.type == "http_tool":
            from app.modules.http_tools.service import resolve
            try:
                resolve(db, workspace_id, node.config, pinned="connection_generation" in node.config or "spec_hash" in node.config)
            except HTTPException as error:
                detail = error.detail if isinstance(error.detail, dict) else {}
                result["errors"].append({"code": detail.get("code", "HTTP_TOOL_UNAVAILABLE"), "message": detail.get("message", "Choose an approved HTTP tool."), "node_id": node.id, "edge_id": None, "path": "config.tool_id"})
            continue
        if node.type == "mcp_tool":
            server_id, tool_name = node.config.get("server_id"), node.config.get("tool_name")
            profile = approved_servers.get(server_id) if isinstance(server_id, str) else None
            connection = db.scalar(select(McpConnection).where(
                McpConnection.workspace_id == workspace_id, McpConnection.server_id == server_id,
            )) if profile and isinstance(tool_name, str) else None
            snapshot = registry.snapshot(connection, tool_name)
            valid = registry.runnable(profile, connection, tool_name)
            if valid and ("connection_generation" in node.config or "input_schema_hash" in node.config):
                valid = node.config.get("connection_generation") == connection.generation and node.config.get("input_schema_hash") == schema_hash(snapshot["input_schema"])
            if not valid:
                result["errors"].append({"code": "MCP_TOOL_UNAVAILABLE", "message": "Connect this MCP server and allow the tool, or republish after its connection changes.", "node_id": node.id, "edge_id": None, "path": "config.tool_name"})
            continue
        if node.type == "llm" and "version_id" not in node.config:
            from app.modules.workflows.llm import issues as llm_issues
            llm_errors, llm_warnings = llm_issues(db, workspace_id, node, mcp_catalog_json)
            result["errors"].extend(llm_errors)
            result["warnings"].extend(llm_warnings)
            if node.config.get("workflow_tools"):
                from app.modules.workflows.tools import expansion
                result["expanded_steps"] += expansion(db, workspace_id, node.config["workflow_tools"], mcp_catalog_json)
            continue
        if node.type in AGENT_NODES:
            try:
                version_id = uuid.UUID(node.config.get("version_id", ""))
            except (ValueError, TypeError, AttributeError):
                version_id = None
            version = db.scalar(
                select(AgentVersion).where(
                    AgentVersion.id == version_id,
                    AgentVersion.workspace_id == workspace_id,
                    AgentVersion.purpose == "published",
                )
            ) if version_id else None
            connection = db.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.id == version.connection_id,
                    IntegrationConnection.workspace_id == workspace_id,
                )
            ) if version else None
            if not version or set(version.config.get("tool_keys", [])) - installed or (
                version.config.get("provider", "openai"), version.config.get("model_id")
            ) not in MODEL_PRICES:
                result["errors"].append({
                    "code": "AGENT_VERSION_UNAVAILABLE", "message": "Select an executable agent version with approved tools.",
                    "node_id": node.id, "edge_id": None, "path": "config.version_id",
                })
            elif not connection or connection.state != "active" or connection.credential_generation != version.credential_generation or version.config["model_id"] not in connection.verified_models:
                result["errors"].append({
                    "code": "AGENT_CREDENTIAL_CHANGED", "message": "The agent credential changed. Publish a new agent version.",
                    "node_id": node.id, "edge_id": None, "path": "config.version_id",
                })
            if version and version.config.get("workflow_tools"):
                from app.modules.workflows.tools import expansion
                result["expanded_steps"] += expansion(db, workspace_id, version.config["workflow_tools"], mcp_catalog_json)
            if version and (version.config.get("mcp_tools") or version.config.get("http_tools") or version.config.get("workflow_tools")):
                from app.modules.agents.tool_grants import validate_grants
                try:
                    validate_grants(db, workspace_id, version.config, mcp_catalog_json)
                except HTTPException as exc:
                    result["errors"].append({"code": exc.detail["code"], "message": exc.detail["message"], "node_id": node.id, "edge_id": None, "path": "config.version_id"})
            continue
        if node.type != "tool":
            continue
        tool_key = node.config.get("tool_key")
        if not isinstance(tool_key, str) or tool_key not in CATALOG:
            result["errors"].append(
                {
                    "code": "TOOL_UNKNOWN",
                    "message": "Select a reviewed tool from the registry.",
                    "node_id": node.id,
                    "edge_id": None,
                    "path": "config.tool_key",
                }
            )
        elif tool_key not in installed:
            result["errors"].append(
                {
                    "code": "TOOL_NOT_APPROVED",
                    "message": "Approve this tool in the workspace before testing.",
                    "node_id": node.id,
                    "edge_id": None,
                    "path": "config.tool_key",
                }
            )
    if result["expanded_steps"] > MAX_EXPANDED_STEPS or result["agent_steps"] > MAX_AGENT_STEPS:
        result["errors"].append({"code": "WORKFLOW_EXPANSION_LIMIT", "message": "The expanded workflow must fit within 120 steps and eight agent calls, including every allowed loop item and branch.", "node_id": None, "edge_id": None, "path": "nodes"})
    if result["pause_seconds"] > MAX_PAUSE_SECONDS:
        result["errors"].append({"code": "WORKFLOW_PAUSE_LIMIT", "message": "Combined approval expiries and timer delays must fit within 24 hours, including all branches and loop items.", "node_id": None, "edge_id": None, "path": "nodes"})
    result["valid"] = not result["errors"]
    result["scope"] = "structural+configuration+tool-approval"
    result["publishable"] = (
        result["valid"]
        and len(graph.nodes) <= 30
        and all(node.type in LOCAL_NODES | COMPOSITE_NODES | PAUSE_NODES | EXTERNAL_NODES for node in graph.nodes)
        and sum(node.type in AGENT_NODES for node in graph.nodes) <= 4
    )
    if result["valid"] and not result["publishable"]:
        result["warnings"].append({"code": "RUNTIME_SIZE_LIMIT", "message": "Published workflows support up to 30 steps and four agent or LLM steps.", "node_id": None, "edge_id": None, "path": None})
    return result


def _pointer(value: object, path: str) -> object:
    if not _safe_pointer(path):
        fail(422, "POINTER_INVALID", "Use a safe JSON Pointer.")
    for raw in path.split("/")[1:] if path else []:
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif (
            isinstance(value, list) and key.isascii() and key.isdecimal() and int(key) < len(value)
        ):
            value = value[int(key)]
        else:
            fail(422, "POINTER_MISSING", "A workflow mapping points to a missing value.")
    return value


def _set_pointer(target: dict, path: str, value: object) -> None:
    if not isinstance(target, dict):
        fail(422, "MAPPING_CONFLICT", "Workflow mappings conflict at the root.")
    if not path.startswith("/") or len(path) > 512:
        fail(422, "POINTER_INVALID", "Mappings must target an object property.")
    parts = [part.replace("~1", "/").replace("~0", "~") for part in path.split("/")[1:]]
    if any(part in {"__proto__", "constructor", "prototype"} for part in parts):
        fail(422, "POINTER_INVALID", "This mapping property is not supported.")
    current = target
    for part in parts[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            fail(422, "MAPPING_CONFLICT", "Workflow mappings conflict at a property.")
        current = child
    current[parts[-1]] = value


def _resolve(reference: dict, data: object, outputs: dict[str, object]) -> object:
    if reference["kind"] != "output":
        return _value(reference, data)
    source = reference.get("node_id")
    if source not in outputs:
        fail(422, "RESULT_SOURCE_INVALID", "Result references a step that has not run.")
    return _pointer(outputs[source], reference.get("pointer", ""))


def _deduplicate(config: dict, data: object) -> dict:
    items = _pointer(data, config["source"])
    if not isinstance(items, list):
        fail(422, "LIST_DEDUPLICATE_INPUT_INVALID", "Remove duplicates needs an array.")
    selected = []
    seen: set[tuple] = set()
    for item in items:
        if "item_pointer" in config and not isinstance(item, dict):
            fail(422, "LIST_DEDUPLICATE_INPUT_INVALID", "A field path requires every list item to be an object.")
        try:
            value = _pointer(item, config["item_pointer"]) if "item_pointer" in config else item
        except HTTPException as error:
            if error.detail.get("code") != "POINTER_MISSING":
                raise
            # Missing fields have no identity; each item survives independently.
            selected.append(item)
            continue
        key = json_equality_key(value)
        if key not in seen:
            seen.add(key)
            selected.append(item)
    return {"items": selected, "count": len(selected), "removed": len(items) - len(selected)}


def run_step(node, data: object, outputs: dict[str, object], agent_handler=None, mcp_handler=None, http_handler=None, composition_handler=None, pause_handler=None) -> dict:
    """Run one node on the data arriving at it; `outputs` holds earlier steps' outputs by node ID."""
    if node.type in {"switch", "list_deduplicate"}:
        bounded_json(data, max_bytes=65536)
    usage = branch = None
    if node.type in ENTRY_NODES:
        output = data
    elif node.type == "tool":
        if not isinstance(data, dict):
            fail(422, "TOOL_INPUT_INVALID", "Tool step input must be a JSON object.")
        output = invoke(node.config["tool_key"], data)
    elif node.type in AGENT_NODES:
        if not isinstance(data, dict) or not agent_handler:
            fail(422, "AGENT_INPUT_INVALID", "Agent step input must be a JSON object.")
        output, usage = agent_handler(node, data)
    elif node.type == "mcp_tool":
        if not isinstance(data, dict) or not mcp_handler:
            fail(422, "MCP_INPUT_INVALID", "MCP tool input must be a JSON object in a published run.")
        output = mcp_handler(node, data)
    elif node.type == "http_tool":
        if not isinstance(data, dict) or not http_handler:
            fail(422, "HTTP_INPUT_INVALID", "HTTP tool input must be a JSON object in a published run.")
        output = http_handler(node, data)
    elif node.type in PAUSE_NODES:
        if not pause_handler:
            fail(422, "PAUSE_REQUIRES_RUN", "Publish and run this workflow to use durable approvals or timers.")
        output = pause_handler(node, data)
    elif node.type in COMPOSITE_NODES:
        if not composition_handler:
            fail(422, "SUBWORKFLOW_HANDLER_REQUIRED", "Run this step through the workflow runtime.")
        output = composition_handler(node, data)
    elif node.type == "merge":
        output = data
    elif node.type == "transform":
        output = {
            name: reference["value"] if reference["kind"] == "literal" else _pointer(data, reference["pointer"])
            for name, reference in node.config["fields"].items()
        }
        schema = node.config.get("output_schema")
        if schema and example_errors(schema, output, "output"):
            fail(422, "TRANSFORM_OUTPUT_INVALID", "Transform output does not match its schema.")
    elif node.type == "condition":
        try:
            left = _value(node.config["left"], data)
        except HTTPException as error:
            if node.config["operator"] == "exists" and error.detail.get("code") == "POINTER_MISSING":
                left = None
            else:
                raise
        right = _value(node.config["right"], data)
        branch = "true" if _compare(left, right, node.config["operator"]) else "false"
        output = data
    elif node.type == "switch":
        value = json_equality_key(_value(node.config["value"], data))
        branch = next((case["id"] for case in node.config["cases"] if json_equality_key(case["value"]) == value), "default")
        output = data
    elif node.type == "text_template":
        def substitute(match, source=data):
            value = _pointer(source, match.group(1))
            return value if isinstance(value, str) else _canonical_text(value)
        output = {"text": re.sub(r"\{\{(.*?)\}\}", substitute, node.config["template"])}
    elif node.type == "list_filter":
        items = _pointer(data, node.config["source"])
        if not isinstance(items, list) or len(items) > 200:
            fail(422, "LIST_FILTER_INPUT_INVALID", "List filter needs an array of at most 200 items.")
        selected = []
        for item in items:
            pointer = node.config.get("item_pointer", "")
            try:
                value = _pointer(item, pointer)
            except HTTPException as error:
                if node.config["operator"] == "exists" and error.detail.get("code") == "POINTER_MISSING":
                    value = None
                else:
                    raise
            if _compare(value, node.config.get("value"), node.config["operator"]):
                selected.append(item)
        output = {"items": selected, "count": len(selected)}
    elif node.type == "list_deduplicate":
        output = _deduplicate(node.config, data)
    elif node.type == "json_parse":
        source = _pointer(data, node.config["source"])
        if not isinstance(source, str) or len(source.encode()) > 65536:
            fail(422, "JSON_PARSE_INPUT_INVALID", "JSON parse needs text smaller than 64 KiB.")
        try:
            parsed = json.loads(source)
        except (ValueError, TypeError):
            fail(422, "JSON_PARSE_INVALID", "The selected text is not valid JSON.")
        output = {"value": parsed}
    elif "fields" in node.config:
        output = {name: _resolve(reference, data, outputs) for name, reference in node.config["fields"].items()}
    else:
        reference = node.config.get("value")
        output = _resolve(reference, data, outputs) if isinstance(reference, dict) and reference.get("kind") == "output" else data
    bounded_json(output, max_bytes=65536)
    step = {"node_id": node.id, "type": node.type, "status": "completed", "output": output}
    if node.type in AGENT_NODES:
        step["usage"] = usage
    if node.type in {"condition", "switch"}:
        step["selected_port"] = branch
    return step


def run_preview(
    db: Session, workspace_id: uuid.UUID, graph: Graph, input_data: dict,
    agent_handler=None, mcp_handler=None, mcp_catalog_json: str = "[]", max_seconds: float = 5,
    checkpoint=None, http_handler=None, composition_handler=None, root_workflow_id=None, pause_handler=None,
) -> dict:
    bounded_json(input_data, max_bytes=65536)
    if example_errors(graph.input_schema, input_data, "input"):
        fail(422, "INPUT_SCHEMA_INVALID", "Preview input does not match the workflow schema.")
    result = validation(db, workspace_id, graph, mcp_catalog_json, root_workflow_id=root_workflow_id)
    if not result["valid"]:
        fail(422, "WORKFLOW_INVALID", result["errors"][0]["message"])
    if not composition_handler and any(node.type in COMPOSITE_NODES for node in graph.nodes) and not result["has_external"]:
        from app.modules.workflows.composition import preview_handler
        composition_handler = preview_handler(db, workspace_id, mcp_catalog_json, time.monotonic() + min(max_seconds, graph.limits.get("timeout_seconds", 60)), (root_workflow_id,) if root_workflow_id else ())
    if not result["publishable"] or any(
        node.type not in (LOCAL_NODES | (PAUSE_NODES if pause_handler else set()) | (COMPOSITE_NODES if composition_handler else set()) | (AGENT_NODES if agent_handler else set()) | ({"mcp_tool"} if mcp_handler else set()) | ({"http_tool"} if http_handler else set())) for node in graph.nodes
    ):
        fail(
            422,
            "PREVIEW_UNSUPPORTED",
            "This workflow shape is not yet supported for preview.",
        )
    outgoing = {node.id: [] for node in graph.nodes}
    incoming = {node.id: [] for node in graph.nodes}
    for edge in graph.edges:
        outgoing[edge.source].append(edge)
        incoming[edge.target].append(edge)
    # Resolve all incoming edges before a join. Execution is deterministic and
    # sequential even when the graph contains fan-out; no implied parallel calls.
    by_id = {node.id: node for node in graph.nodes}
    remaining = {node.id: len(incoming[node.id]) for node in graph.nodes}
    ready = [node.id for node in graph.nodes if remaining[node.id] == 0]
    steps = []
    outputs: dict[str, object] = {}
    selected_ports: dict[str, str] = {}
    final_output = None
    result_completed = False
    restored = checkpoint.completed() if checkpoint else {}
    started = time.monotonic()
    while ready:
        current = by_id[ready.pop(0)]
        if time.monotonic() - started > max_seconds:
            fail(408, "PREVIEW_TIMEOUT", "Workflow exceeded its execution time limit.")
        active = [edge for edge in incoming[current.id] if edge.source in outputs and selected_ports[edge.source] == edge.source_port]
        mode = current.config["mode"] if current.type == "merge" else "active" if current.type == "result" else current.join
        skipped = current.type not in ENTRY_NODES and (not active or mode == "all" and len(active) != len(incoming[current.id]))
        if current.id in restored:
            step = restored[current.id]
            if (step["status"] == "skipped") != skipped:
                fail(409, "CHECKPOINT_CONFLICT", "Saved workflow progress does not match the active paths.")
            steps.append(step)
            if not skipped:
                outputs[current.id] = step["output"]
                selected_ports[current.id] = step.get("selected_port", "out")
                if current.type == "result":
                    final_output, result_completed = step["output"], True
        elif skipped:
            step = {"node_id": current.id, "type": current.type, "status": "skipped", "output": None}
            if checkpoint:
                checkpoint.finish(current, None, step, len(steps))
            steps.append(step)
        else:
            data = None
            try:
                values = {}
                for edge in active:
                    output = outputs[edge.source]
                    mapped = {} if edge.mappings else output
                    for mapping in edge.mappings:
                        if mapping["to"] == "":
                            mapped = _pointer(output, mapping["from"])
                        else:
                            _set_pointer(mapped, mapping["to"], _pointer(output, mapping["from"]))
                    values[edge.source] = mapped
                data = input_data if current.type in ENTRY_NODES else next(iter(values.values())) if len(values) == 1 else values
                data = deepcopy(data)
                bounded_json(data, max_bytes=65536)
                for attempt in range(current.policy.get("max_attempts", 1)):
                    if time.monotonic() - started > min(max_seconds, graph.limits.get("timeout_seconds", 60)):
                        fail(408, "PREVIEW_TIMEOUT", "Workflow exceeded its execution time limit.")
                    if checkpoint:
                        checkpoint.start(current, data, len(steps))
                    began = time.monotonic()
                    try:
                        if current.type in PAUSE_NODES:
                            step = run_step(current, deepcopy(data), outputs, pause_handler=pause_handler)
                        else:
                            step = run_step(current, deepcopy(data), outputs, agent_handler, mcp_handler, http_handler, composition_handler)
                        if time.monotonic() - began > current.policy.get("timeout_seconds", 60):
                            fail(408, "STEP_TIMEOUT", "This step exceeded its configured execution timeout.")
                        break
                    except HTTPException as exc:
                        code = exc.detail.get("code") if isinstance(exc.detail, dict) else None
                        retryable = current.type in LOCAL_NODES and code in {"STEP_TIMEOUT", "LOCAL_TOOL_TEMPORARILY_UNAVAILABLE"}
                        if not retryable or attempt + 1 >= current.policy.get("max_attempts", 1):
                            raise
                        if checkpoint:
                            checkpoint.finish(current, data, {"node_id": current.id, "type": current.type, "status": "failed", "output": None, "error_code": code}, len(steps))
                        time.sleep(0.05 * (attempt + 1))
                if checkpoint:
                    checkpoint.finish(current, data, step, len(steps))
            except Parked:
                raise
            except Exception as exc:
                code = exc.detail.get("code", "WORKFLOW_STEP_FAILED") if isinstance(exc, HTTPException) and isinstance(exc.detail, dict) else getattr(exc, "code", "WORKFLOW_STEP_FAILED")
                if checkpoint:
                    checkpoint.finish(current, data, {"node_id": current.id, "type": current.type, "status": "failed", "output": None, "error_code": code}, len(steps))
                raise
            outputs[current.id] = step["output"]
            selected_ports[current.id] = step.get("selected_port", "out")
            steps.append(step)
            if current.type == "result":
                final_output = step["output"]
                result_completed = True
        for edge in outgoing[current.id]:
            remaining[edge.target] -= 1
            if remaining[edge.target] == 0:
                ready.append(edge.target)
    if not result_completed:
        fail(422, "RESULT_SKIPPED", "No active path reached the result. Use an active-path merge after conditional branches.")
    if example_errors(graph.output_schema, final_output, "output"):
        fail(422, "OUTPUT_SCHEMA_INVALID", "Workflow output does not match its schema.")
    durable = bool(checkpoint or agent_handler or mcp_handler or http_handler)
    return {"output": final_output, "steps": steps, "scope": "durable" if durable else "preview", "durable": durable}
