"""Bounded synchronous preview for linear workflows with reviewed local tools."""

import json
import re
import time
import uuid
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import fail
from app.core.json_contracts import bounded_json, example_errors, validate_user_schema
from app.modules.agents.models import AgentVersion
from app.modules.executions.service import MODEL_PRICES
from app.modules.integrations.models import IntegrationConnection
from app.modules.mcp.catalog import catalog
from app.modules.mcp.models import McpConnection
from app.modules.mcp.service import schema_hash
from app.modules.tools.catalog import CATALOG, invoke
from app.modules.tools.models import ToolInstallation
from app.modules.workflows.domain import validate_graph
from app.modules.workflows.schemas import Graph


def _transform_errors(node) -> list[dict]:
    fields = node.config.get("fields")
    if not isinstance(fields, dict) or not 1 <= len(fields) <= 32:
        return [{"code": "TRANSFORM_INVALID", "message": "Define 1–32 output fields.", "node_id": node.id, "edge_id": None, "path": "config.fields"}]
    for name, reference in fields.items():
        if not isinstance(name, str) or not name or len(name) > 100 or name in {"__proto__", "constructor", "prototype"} or not isinstance(reference, dict):
            return [{"code": "TRANSFORM_INVALID", "message": "Transform fields need safe names and value references.", "node_id": node.id, "edge_id": None, "path": "config.fields"}]
        kind = reference.get("kind")
        if kind == "literal" and set(reference) == {"kind", "value"}:
            continue
        if kind == "input" and set(reference) == {"kind", "pointer"} and _safe_pointer(reference["pointer"]):
            continue
        return [{"code": "TRANSFORM_INVALID", "message": "Use literal values or input JSON Pointers in transform fields.", "node_id": node.id, "edge_id": None, "path": f"config.fields.{name}"}]
    schema = node.config.get("output_schema")
    if schema is not None and (not isinstance(schema, dict) or schema.get("type") != "object"):
        return [{"code": "TRANSFORM_INVALID", "message": "The transform output schema must describe an object.", "node_id": node.id, "edge_id": None, "path": "config.output_schema"}]
    try:
        bounded_json(fields, max_bytes=65536)
        if schema is not None:
            validate_user_schema(schema)
    except HTTPException:
        return [{"code": "TRANSFORM_INVALID", "message": "Transform configuration exceeds supported JSON or schema limits.", "node_id": node.id, "edge_id": None, "path": "config"}]
    return []


def _safe_pointer(path: object) -> bool:
    return isinstance(path, str) and len(path) <= 512 and (not path or path.startswith("/")) and all(
        part.replace("~1", "/").replace("~0", "~") not in {"__proto__", "constructor", "prototype"}
        for part in path.split("/")[1:]
    )


OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "contains", "exists"}
ENTRY_NODES = {"manual_input", "webhook_trigger", "schedule_trigger"}
LOCAL_NODES = ENTRY_NODES | {"tool", "transform", "condition", "text_template", "list_filter", "json_parse", "result"}


def _configuration_errors(node) -> list[dict]:
    config = node.config
    def issue(message: str) -> list[dict]:
        return [{"code": "NODE_CONFIG_INVALID", "message": message, "node_id": node.id, "edge_id": None, "path": "config"}]
    if node.type == "condition":
        if config.get("operator") not in OPERATORS or not all(_reference_valid(config.get(side)) for side in ("left", "right")):
            return issue("Condition needs a supported operator and two literal or input references.")
    elif node.type == "text_template":
        template = config.get("template")
        if not isinstance(template, str) or not 1 <= len(template) <= 4096 or len(re.findall(r"\{\{(.*?)\}\}", template)) > 32 or any(not _safe_pointer(pointer) for pointer in re.findall(r"\{\{(.*?)\}\}", template)):
            return issue("Template needs 1–4096 characters and at most 32 safe JSON Pointer placeholders.")
    elif node.type == "list_filter":
        if not _safe_pointer(config.get("source")) or not _safe_pointer(config.get("item_pointer", "")) or config.get("operator") not in OPERATORS:
            return issue("List filter needs a source pointer, item pointer and supported operator.")
        if config.get("operator") != "exists" and "value" not in config:
            return issue("List filter needs a comparison value.")
    elif node.type == "json_parse":
        if not _safe_pointer(config.get("source")):
            return issue("JSON parse needs a source pointer to text.")
    try:
        bounded_json(config, max_bytes=65536)
    except HTTPException:
        return issue("Node configuration exceeds supported JSON limits.")
    return []


def _reference_valid(reference: object) -> bool:
    return isinstance(reference, dict) and (
        (reference.get("kind") == "literal" and set(reference) == {"kind", "value"})
        or (reference.get("kind") == "input" and set(reference) == {"kind", "pointer"} and _safe_pointer(reference["pointer"]))
    )


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


def validation(db: Session, workspace_id: uuid.UUID, graph: Graph, mcp_catalog_json: str = "[]") -> dict:
    result = validate_graph(graph)
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
    approved_servers = catalog(mcp_catalog_json)
    for node in graph.nodes:
        if node.type == "mcp_tool":
            server_id, tool_name = node.config.get("server_id"), node.config.get("tool_name")
            profile = approved_servers.get(server_id) if isinstance(server_id, str) else None
            connection = db.scalar(select(McpConnection).where(
                McpConnection.workspace_id == workspace_id, McpConnection.server_id == server_id,
            )) if profile and isinstance(tool_name, str) else None
            snapshot = next((item for item in connection.tool_snapshots if item["name"] == tool_name), None) if connection and connection.state == "active" else None
            valid = bool(profile and tool_name in profile.get("read_only_tools", []) and connection and connection.state == "active" and tool_name in connection.verified_tools and snapshot)
            if valid and ("connection_generation" in node.config or "input_schema_hash" in node.config):
                valid = node.config.get("connection_generation") == connection.generation and node.config.get("input_schema_hash") == schema_hash(snapshot["input_schema"])
            if not valid:
                result["errors"].append({"code": "MCP_TOOL_UNAVAILABLE", "message": "Connect an operator-approved read-only MCP tool, or republish after its connection changes.", "node_id": node.id, "edge_id": None, "path": "config"})
            continue
        if node.type == "transform":
            result["errors"].extend(_transform_errors(node))
            continue
        if node.type in {"condition", "text_template", "list_filter", "json_parse"}:
            result["errors"].extend(_configuration_errors(node))
            continue
        if node.type == "agent":
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
    result["valid"] = not result["errors"]
    result["scope"] = "structural+tool-approval"
    outgoing = {node.id: [] for node in graph.nodes}
    incoming = {node.id: [] for node in graph.nodes}
    for edge in graph.edges:
        if edge.source in outgoing and edge.target in incoming:
            outgoing[edge.source].append(edge)
            incoming[edge.target].append(edge)
    conditions = [node for node in graph.nodes if node.type == "condition"]
    # One decision may fork into two linear paths that join only at the result.
    branch_shape = len(conditions) <= 1 and all(
        len(incoming[node.id]) == (0 if node.type in ENTRY_NODES else (2 if node.type == "result" and conditions else 1))
        and len(outgoing[node.id]) == (0 if node.type == "result" else (2 if node.type == "condition" else 1))
        for node in graph.nodes
    )
    result["publishable"] = (
        result["valid"]
        and len(graph.nodes) <= 12
        and len(graph.edges) == len(graph.nodes) - 1 + len(conditions)
        and all(node.type in LOCAL_NODES | {"agent", "mcp_tool"} for node in graph.nodes)
        and sum(node.type == "agent" for node in graph.nodes) <= 1
        and branch_shape
    )
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


def run_preview(
    db: Session, workspace_id: uuid.UUID, graph: Graph, input_data: dict,
    agent_handler=None, mcp_handler=None, mcp_catalog_json: str = "[]", max_seconds: float = 5,
) -> dict:
    bounded_json(input_data, max_bytes=65536)
    if example_errors(graph.input_schema, input_data, "input"):
        fail(422, "INPUT_SCHEMA_INVALID", "Preview input does not match the workflow schema.")
    result = validation(db, workspace_id, graph, mcp_catalog_json)
    if not result["valid"]:
        fail(422, "WORKFLOW_INVALID", result["errors"][0]["message"])
    if not result["publishable"] or any(
        node.type not in (LOCAL_NODES | ({"agent"} if agent_handler else set()) | ({"mcp_tool"} if mcp_handler else set())) for node in graph.nodes
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
    current = next(node for node in graph.nodes if node.type in ENTRY_NODES)
    data: object = input_data
    steps = []
    outputs: dict[str, object] = {}
    started = time.monotonic()
    while True:
        if time.monotonic() - started > max_seconds:
            fail(408, "PREVIEW_TIMEOUT", "Workflow preview exceeded five seconds.")
        if current.type in ENTRY_NODES:
            output = data
        elif current.type == "tool":
            if not isinstance(data, dict):
                fail(422, "TOOL_INPUT_INVALID", "Tool step input must be a JSON object.")
            output = invoke(current.config["tool_key"], data)
        elif current.type == "agent":
            if not isinstance(data, dict) or not agent_handler:
                fail(422, "AGENT_INPUT_INVALID", "Agent step input must be a JSON object.")
            output, usage = agent_handler(current, data)
        elif current.type == "mcp_tool":
            if not isinstance(data, dict) or not mcp_handler:
                fail(422, "MCP_INPUT_INVALID", "MCP tool input must be a JSON object in a published run.")
            output = mcp_handler(current, data)
        elif current.type == "transform":
            output = {
                name: reference["value"] if reference["kind"] == "literal" else _pointer(data, reference["pointer"])
                for name, reference in current.config["fields"].items()
            }
            schema = current.config.get("output_schema")
            if schema and example_errors(schema, output, "output"):
                fail(422, "TRANSFORM_OUTPUT_INVALID", "Transform output does not match its schema.")
        elif current.type == "condition":
            try:
                left = _value(current.config["left"], data)
            except HTTPException as error:
                if current.config["operator"] == "exists" and error.detail.get("code") == "POINTER_MISSING":
                    left = None
                else:
                    raise
            right = _value(current.config["right"], data)
            branch = "true" if _compare(left, right, current.config["operator"]) else "false"
            output = data
        elif current.type == "text_template":
            def substitute(match, source=data):
                value = _pointer(source, match.group(1))
                return value if isinstance(value, str) else _canonical_text(value)
            output = {"text": re.sub(r"\{\{(.*?)\}\}", substitute, current.config["template"])}
        elif current.type == "list_filter":
            items = _pointer(data, current.config["source"])
            if not isinstance(items, list) or len(items) > 200:
                fail(422, "LIST_FILTER_INPUT_INVALID", "List filter needs an array of at most 200 items.")
            selected = []
            for item in items:
                pointer = current.config.get("item_pointer", "")
                try:
                    value = _pointer(item, pointer)
                except HTTPException as error:
                    if current.config["operator"] == "exists" and error.detail.get("code") == "POINTER_MISSING":
                        value = None
                    else:
                        raise
                if _compare(value, current.config.get("value"), current.config["operator"]):
                    selected.append(item)
            output = {"items": selected, "count": len(selected)}
        elif current.type == "json_parse":
            source = _pointer(data, current.config["source"])
            if not isinstance(source, str) or len(source.encode()) > 65536:
                fail(422, "JSON_PARSE_INPUT_INVALID", "JSON parse needs text smaller than 64 KiB.")
            try:
                parsed = json.loads(source)
            except (ValueError, TypeError):
                fail(422, "JSON_PARSE_INVALID", "The selected text is not valid JSON.")
            output = {"value": parsed}
        else:
            reference = current.config.get("value")
            if isinstance(reference, dict) and reference.get("kind") == "output":
                source = reference.get("node_id")
                if source not in outputs:
                    fail(422, "RESULT_SOURCE_INVALID", "Result references a step that has not run.")
                output = _pointer(outputs[source], reference.get("pointer", ""))
            else:
                output = data
        bounded_json(output, max_bytes=65536)
        outputs[current.id] = output
        step = {"node_id": current.id, "type": current.type, "status": "completed", "output": output}
        if current.type == "agent":
            step["usage"] = usage
        if current.type == "condition":
            step["selected_port"] = branch
        steps.append(step)
        if current.type == "result":
            if example_errors(graph.output_schema, output, "output"):
                fail(
                    422,
                    "OUTPUT_SCHEMA_INVALID",
                    "Preview output does not match the workflow schema.",
                )
            durable = bool(agent_handler or mcp_handler)
            return {"output": output, "steps": steps, "scope": "durable" if durable else "preview", "durable": durable}
        edge = next(e for e in outgoing[current.id] if e.source_port == branch) if current.type == "condition" else outgoing[current.id][0]
        target = next(node for node in graph.nodes if node.id == edge.target)
        if edge.mappings:
            mapped = {}
            for mapping in edge.mappings:
                if mapping["to"] == "":
                    mapped = _pointer(output, mapping["from"])
                else:
                    _set_pointer(mapped, mapping["to"], _pointer(output, mapping["from"]))
            data = mapped
        else:
            data = output
        current = target
