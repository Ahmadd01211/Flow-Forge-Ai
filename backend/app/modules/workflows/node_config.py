"""Node configuration contracts: one JSON Schema per node type plus checks a schema cannot express.

These mirror exactly what run_preview reads. Trigger nodes carry no configuration: delivery is
bound through deployments, so trigger secrets never enter a workflow graph.
"""

import re
from typing import get_args

from fastapi import HTTPException
from jsonschema import Draft202012Validator

from app.core.json_contracts import UNSAFE_NAMES, bounded_json, validate_user_schema
from app.modules.agents.schemas import AgentConfig
from app.modules.tools.catalog import CATALOG
from app.modules.workflows.domain import switch_ports

OPERATORS = ["eq", "ne", "gt", "gte", "lt", "lte", "contains", "exists"]
ORDERING = {"gt", "gte", "lt", "lte"}
PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}")
# A decoded segment can only spell an unsafe name if the raw segment does: none contain ~ or /.
POINTER_PATTERN = r"^(?:/(?!(?:__proto__|constructor|prototype)(?:/|$))[^/]*)*$"


def _pointer(message: str) -> dict:
    return {"type": "string", "maxLength": 512, "pattern": POINTER_PATTERN, "x-message": message}


INPUT_FIELD = _pointer("Use a field path such as /ticket/priority, or leave it empty for the whole input.")
REFERENCE = {
    "x-message": "Choose a fixed value or a field from this step's input.",
    "oneOf": [
        {
            "type": "object",
            "properties": {"kind": {"const": "literal"}, "value": {"x-message": "Enter a fixed value."}},
            "required": ["kind", "value"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"kind": {"const": "input"}, "pointer": INPUT_FIELD},
            "required": ["kind", "pointer"],
            "additionalProperties": False,
        },
    ],
}
OPERATOR = {"enum": OPERATORS, "x-message": "Choose a supported comparison."}
FIELD_NAMES = {
    "minLength": 1,
    "maxLength": 100,
    "not": {"enum": sorted(UNSAFE_NAMES)},
    "x-message": "Field names need 1–100 characters and cannot be reserved names.",
}
STEP_OUTPUT = {
    "type": "object",
    "properties": {
        "kind": {"const": "output", "x-message": "Return the output of an earlier step."},
        "node_id": {"type": "string", "minLength": 1, "x-message": "Choose the step whose output is returned."},
        "pointer": _pointer("Use a field path such as /summary, or leave it empty for the whole output."),
    },
    "required": ["kind", "node_id"],
    "additionalProperties": False,
    "x-message": "Choose which step's output to return.",
}
# Result fields may also read the incoming data or a fixed value, like a transform.
RESULT_REFERENCE = {**REFERENCE, "oneOf": [*REFERENCE["oneOf"], STEP_OUTPUT], "x-message": "Choose incoming data, a step's output or a fixed value."}
NO_CONFIG = {"type": "object", "properties": {}}
WORKFLOW_VERSION = {"type": "string", "pattern": r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", "x-message": "Select a published workflow version."}
GRAPH_HASH = {"type": "string", "pattern": "^[a-f0-9]{64}$", "x-message": "Republish to pin this workflow contract."}

SCHEMAS: dict[str, dict] = {
    "approval": {"type": "object", "properties": {"prompt": {"type": "string", "minLength": 1, "maxLength": 500, "pattern": r"\S", "x-message": "Describe the decision in 1–500 characters; do not include secrets."}, "expires_seconds": {"type": "integer", "minimum": 60, "maximum": 86400, "x-message": "Allow 60–86,400 seconds for a decision."}, "allow_requester": {"type": "boolean"}}, "required": ["prompt", "expires_seconds", "allow_requester"]},
    "wait": {"type": "object", "properties": {"seconds": {"type": "integer", "minimum": 1, "maximum": 86400, "x-message": "Wait for 1–86,400 seconds."}}, "required": ["seconds"]},
    "subworkflow": {"type": "object", "properties": {"version_id": WORKFLOW_VERSION, "graph_hash": GRAPH_HASH}, "required": ["version_id"]},
    "for_each": {"type": "object", "properties": {"version_id": WORKFLOW_VERSION, "graph_hash": GRAPH_HASH, "source": INPUT_FIELD, "max_items": {"type": "integer", "minimum": 1, "maximum": 20, "x-message": "Allow between 1 and 20 items; oversized input is rejected."}, "input_mode": {"enum": ["item", "envelope"], "x-message": "Send an item object or an item/index envelope."}}, "required": ["version_id", "source", "max_items", "input_mode"]},
    "manual_input": NO_CONFIG,
    "webhook_trigger": NO_CONFIG,
    "schedule_trigger": NO_CONFIG,
    "chat_trigger": NO_CONFIG,
    "merge": {"type": "object", "properties": {"mode": {"enum": ["all", "active"], "x-message": "Choose all paths or only active paths."}}, "required": ["mode"]},
    "agent": {
        "type": "object",
        "properties": {
            "version_id": {
                "type": "string",
                "pattern": r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
                "x-message": "Choose a published agent version.",
            }
        },
        "required": ["version_id"],
    },
    # Shapes only; provider, model and tool readiness come from the agent checklist in llm.issues.
    "llm": {
        "type": "object",
        "properties": {
            "instructions": {"type": "string", "minLength": 1, "maxLength": 32000, "x-message": "Tell the model what to do, in up to 32,000 characters."},
            "provider": {"enum": list(get_args(AgentConfig.model_fields["provider"].annotation)), "x-message": "Choose a model provider."},
            "model_id": {"type": "string", "minLength": 1, "maxLength": 200, "x-message": "Choose a verified model."},
            "tool_keys": {"type": "array", "maxItems": 8, "uniqueItems": True, "items": {"enum": sorted(CATALOG)}, "x-message": "Choose each reviewed tool once."},
            "mcp_tools": {
                "type": "array", "maxItems": 8,
                "items": {"type": "object", "properties": {"server_id": {"type": "string"}, "tool_name": {"type": "string"}}, "required": ["server_id", "tool_name"]},
                "x-message": "Choose up to eight MCP tools.",
            },
            "http_tools": {
                "type": "array", "maxItems": 8,
                "items": {"type": "object", "properties": {"tool_id": {"type": "string"}}, "required": ["tool_id"]},
                "x-message": "Choose up to eight HTTP tools.",
            },
            "output_schema": {"type": "object", "x-message": "Describe the output with a JSON Schema object."},
            "limits": {
                "type": "object",
                "properties": {
                    "max_cost_usd": {"type": "string", "pattern": r"^(0|[1-9][0-9]{0,3})(\.[0-9]{1,8})?$", "x-message": "Enter a dollar amount such as 0.10."},
                    "max_tool_calls": {"type": "integer", "minimum": 0, "maximum": 32, "x-message": "Allow 0–32 tool calls."},
                    "max_iterations": {"type": "integer", "minimum": 1, "maximum": 20, "x-message": "Allow 1–20 model turns."},
                    "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300, "x-message": "Use 1–300 seconds."},
                    "max_output_tokens": {"type": "integer", "minimum": 16, "maximum": 4096, "x-message": "Use 16–4,096 output tokens."},
                },
                "additionalProperties": False,
                "x-message": "Check the run limits.",
            },
            "memory": {
                "type": ["object", "null"],
                "properties": {
                    "key_pointer": {**_pointer("Use a field path such as /conversation_id."), "minLength": 2},
                    "max_turns": {"type": "integer", "minimum": 1, "maximum": 20, "x-message": "Remember 1–20 exchanges."},
                    "retention_days": {"type": "integer", "minimum": 1, "maximum": 90, "x-message": "Keep memory for 1–90 days."},
                },
                "additionalProperties": False,
                "x-message": "Check the memory settings.",
            },
            "skills": {
                "type": "array", "maxItems": 8,
                "items": {"type": "object", "properties": {"skill_id": {"type": "string"}}, "required": ["skill_id"]},
                "x-message": "Attach up to eight skills.",
            },
            "workflow_tools": {
                "type": "array", "maxItems": 4,
                "items": {"type": "object", "properties": {"version_id": {"type": "string"}}, "required": ["version_id"]},
                "x-message": "Offer up to four published workflows as tools.",
            },
            # Pinned when the workflow is published.
            "version_id": {"type": "string", "x-message": "Republish to refresh this LLM step."},
        },
        "required": ["instructions", "provider", "model_id"],
    },
    "tool": {
        "type": "object",
        "properties": {
            "tool_key": {"enum": sorted(CATALOG), "x-message": "Choose a reviewed tool from the registry."}
        },
        "required": ["tool_key"],
    },
    "http_tool": {
        "type": "object",
        "properties": {
            "tool_id": {"type": "string", "pattern": r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", "x-message": "Choose an approved HTTP tool."},
            "connection_generation": {"type": "integer", "minimum": 1},
            "spec_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        },
        "required": ["tool_id"],
    },
    "mcp_tool": {
        "type": "object",
        "properties": {
            "server_id": {"type": "string", "minLength": 1, "maxLength": 100, "x-message": "Choose a connected MCP tool."},
            "tool_name": {"type": "string", "minLength": 1, "maxLength": 200, "x-message": "Choose a connected MCP tool."},
            # Pinned by publish; drafts normally omit them.
            "connection_generation": {"type": "integer", "x-message": "Republish to pin the current connection."},
            "input_schema_hash": {"type": "string", "x-message": "Republish to pin the current tool schema."},
        },
        "required": ["server_id", "tool_name"],
    },
    "condition": {
        "type": "object",
        "properties": {"left": REFERENCE, "operator": OPERATOR, "right": REFERENCE},
        "required": ["left", "operator", "right"],
    },
    "switch": {
        "type": "object",
        "properties": {
            "value": REFERENCE,
            "cases": {
                "type": "array", "minItems": 1, "maxItems": 8,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{0,31}$"},
                        "label": {"type": "string", "minLength": 1, "maxLength": 40},
                        "value": {"type": ["string", "number", "boolean", "null"]},
                    },
                    "required": ["id", "label", "value"], "additionalProperties": False,
                },
                "x-message": "Add between one and eight cases with unique IDs and values.",
            },
        },
        "required": ["value", "cases"],
    },
    "transform": {
        "type": "object",
        "properties": {
            "fields": {
                "type": "object",
                "minProperties": 1,
                "maxProperties": 32,
                "propertyNames": FIELD_NAMES,
                "additionalProperties": REFERENCE,
                "x-message": "Add between 1 and 32 output fields.",
            },
            "output_schema": {"type": "object", "x-message": "The output schema must be a JSON Schema object."},
        },
        "required": ["fields"],
    },
    "text_template": {
        "type": "object",
        "properties": {
            "template": {"type": "string", "minLength": 1, "maxLength": 4096, "x-message": "Write between 1 and 4,096 characters."}
        },
        "required": ["template"],
    },
    "list_filter": {
        "type": "object",
        "properties": {
            "source": _pointer("Choose the input field that holds the list, such as /items."),
            "item_pointer": _pointer("Use a path inside each item such as /status, or leave it empty to compare the item itself."),
            "operator": OPERATOR,
            "value": {"x-message": "Enter the value to compare each item with."},
        },
        "required": ["source", "operator"],
        "if": {"properties": {"operator": {"const": "exists"}}, "required": ["operator"]},
        "else": {"required": ["value"]},
    },
    "list_deduplicate": {
        "type": "object",
        "properties": {
            "source": _pointer("Choose the input field that holds the list, such as /items."),
            "item_pointer": _pointer("Choose a path inside each object, or omit it to compare whole items."),
        },
        "required": ["source"],
    },
    "json_parse": {
        "type": "object",
        "properties": {"source": _pointer("Choose the input field that holds JSON text, such as /text.")},
        "required": ["source"],
    },
    "result": {
        "type": "object",
        "properties": {
            "value": STEP_OUTPUT,
            "fields": {
                "type": "object",
                "minProperties": 1,
                "maxProperties": 32,
                "propertyNames": FIELD_NAMES,
                "additionalProperties": RESULT_REFERENCE,
                "x-message": "Add between 1 and 32 result fields.",
            },
        },
        "not": {"required": ["value", "fields"]},
        "x-message": "Return either one step's output or a set of fields, not both.",
    },
}
VALIDATORS = {kind: Draft202012Validator(schema) for kind, schema in SCHEMAS.items()}


def _leaf(error, inherited: str):
    """Descend into the oneOf branch whose `kind` matches, so the message names the actual field."""
    message = error.schema.get("x-message", inherited) if isinstance(error.schema, dict) else inherited
    if error.validator == "oneOf" and error.context and isinstance(error.instance, dict):
        for index, branch in enumerate(error.validator_value):
            if branch.get("properties", {}).get("kind", {}).get("const") == error.instance.get("kind"):
                matching = [item for item in error.context if item.relative_schema_path[0] == index]
                if matching:
                    return _leaf(matching[0], message)
    return error, message


def _path(parts) -> str:
    return ".".join(["config", *(str(part) for part in parts)])


def config_issues(
    node, upstream: set[str] | None = None, always: set[str] | None = None
) -> tuple[list[dict], list[dict]]:
    """Return (errors, warnings) for one node.

    For a result, `upstream` lists the steps that can run before it and `always` those that run on
    every path to it; omit both to skip graph-dependent checks.
    """
    code = "TRANSFORM_INVALID" if node.type == "transform" else "NODE_CONFIG_INVALID"
    errors: dict[str, str] = {}
    warnings: list[dict] = []

    def error(path: str, message: str) -> None:
        errors.setdefault(path, message)

    timeout = node.policy.get("timeout_seconds", 60)
    attempts = node.policy.get("max_attempts", 1)
    if type(timeout) is not int or not 1 <= timeout <= 300:
        error("policy.timeout_seconds", "Step timeout must be a whole number from 1 to 300 seconds.")
    if type(attempts) is not int or not 1 <= attempts <= 3:
        error("policy.max_attempts", "Use one to three attempts for local steps.")
    elif node.type in {"agent", "llm", "mcp_tool", "http_tool", "subworkflow", "for_each", "approval", "wait"} and attempts != 1:
        error("policy.max_attempts", "External steps require one attempt. Start an explicit new run to replay them.")
    config = node.config
    try:
        bounded_json(config, max_bytes=65536)
    except HTTPException as exc:
        error("config", exc.detail["message"])
    schema = SCHEMAS[node.type]
    if not errors:
        for raw in VALIDATORS[node.type].iter_errors(config):
            leaf, message = _leaf(raw, "Check this setting.")
            if leaf.validator == "required":
                # Top-level if/else clauses carry no properties of their own.
                properties = leaf.schema.get("properties") or ({} if leaf.absolute_path else schema["properties"])
                for key in leaf.validator_value:
                    if isinstance(leaf.instance, dict) and key not in leaf.instance:
                        error(_path([*leaf.absolute_path, key]), properties.get(key, {}).get("x-message", message))
            else:
                error(_path(leaf.absolute_path), message)
        # The runtime ignores unknown top-level keys, so they warn instead of blocking.
        for key in sorted(set(config) - set(schema["properties"])):
            warnings.append({
                "code": "NODE_CONFIG_UNUSED", "message": f"“{key}” is not used by this step and will be ignored.",
                "node_id": node.id, "edge_id": None, "path": f"config.{key}",
            })
    def warn(path: str, message: str) -> None:
        warnings.append({"code": "NODE_SOURCE_CONDITIONAL", "message": message, "node_id": node.id, "edge_id": None, "path": path})

    if not errors:
        _semantic(node.type, config, upstream, always, error, warn)
    return (
        [{"code": code, "message": message, "node_id": node.id, "edge_id": None, "path": path} for path, message in errors.items()],
        warnings,
    )


def _semantic(kind: str, config: dict, upstream: set[str] | None, always: set[str] | None, error, warn) -> None:
    if kind == "switch":
        try:
            switch_ports(config)
        except ValueError as exc:
            error("config.cases", str(exc))
    elif kind == "text_template":
        placeholders = PLACEHOLDER.findall(config["template"])
        if len(placeholders) > 32:
            error("config.template", "Use at most 32 placeholders.")
        for placeholder in placeholders:
            if not _safe_pointer(placeholder):
                error("config.template", f"Placeholder {{{{{placeholder}}}}} must be a field path such as {{{{/ticket/id}}}}.")
                break
    elif kind == "transform" and "output_schema" in config:
        try:
            validate_user_schema(config["output_schema"])
        except HTTPException as exc:
            error("config.output_schema", exc.detail["message"])
    elif kind in ("condition", "list_filter") and config["operator"] in ORDERING:
        literals = (
            {f"config.{side}": config[side]["value"] for side in ("left", "right") if config[side]["kind"] == "literal"}
            if kind == "condition" else {"config.value": config["value"]}
        )
        for path, value in literals.items():
            if type(value) not in (str, int, float):
                error(path, "Greater/less-than comparisons need a number or text value.")
    elif kind == "result" and upstream is not None:
        sources = {"config.value": config["value"]} if "value" in config else {
            f"config.fields.{name}": reference for name, reference in config.get("fields", {}).items()
            if reference["kind"] == "output"
        }
        for path, reference in sources.items():
            if reference["node_id"] not in upstream:
                error(f"{path}.node_id", "Choose a step that runs before this result.")
            elif always is not None and reference["node_id"] not in always:
                warn(f"{path}.node_id", "This step is skipped on some paths, and the run fails when it was. Use incoming data to merge branches.")


def _safe_pointer(path: str) -> bool:
    return len(path) <= 512 and re.fullmatch(POINTER_PATTERN, path) is not None
