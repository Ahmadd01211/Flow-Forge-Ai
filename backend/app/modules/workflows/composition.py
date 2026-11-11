"""Small, explicit composition contracts; published workspace versions are the only call targets."""

import hashlib
import json
import time
import uuid

from sqlalchemy import select

from app.core.errors import fail
from app.core.json_contracts import bounded_json, example_errors
from app.modules.workflows.models import WorkflowVersion
from app.modules.workflows.schemas import Graph

COMPOSITE_NODES = {"subworkflow", "for_each"}
MAX_EXPANDED_STEPS = 120
MAX_AGENT_STEPS = 8
MAX_CALL_DEPTH = 3  # Root, child, grandchild.
MAX_ITEMS = 20


def resolve_version(db, workspace_id, config, cache=None):
    try:
        identity = uuid.UUID(config["version_id"])
    except (KeyError, ValueError, TypeError, AttributeError):
        fail(
            422,
            "SUBWORKFLOW_VERSION_REQUIRED",
            "Select a published workflow version from this workspace.",
        )
    cache = cache if cache is not None else {}
    if identity not in cache:
        if len(cache) >= 24:
            fail(
                422,
                "SUBWORKFLOW_DEPENDENCY_LIMIT",
                "Use no more than 24 distinct workflow dependencies.",
            )
        cache[identity] = db.scalar(
            select(WorkflowVersion).where(
                WorkflowVersion.workspace_id == workspace_id, WorkflowVersion.id == identity
            )
        )
    version = cache[identity]
    if not version or version.workspace_id != workspace_id:
        fail(
            404,
            "SUBWORKFLOW_UNAVAILABLE",
            "This published workflow version is unavailable in the workspace.",
        )
    actual = hashlib.sha256(
        json.dumps(
            version.graph, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    if actual != version.graph_hash or (
        "graph_hash" in config and config["graph_hash"] != version.graph_hash
    ):
        fail(
            409,
            "SUBWORKFLOW_CHANGED",
            "The selected workflow version no longer matches its published contract.",
        )
    return version, Graph.model_validate(version.graph)


def inputs_for(node, data, graph):
    from app.modules.workflows.preview import _pointer

    if not isinstance(data, dict):
        fail(422, "SUBWORKFLOW_INPUT_INVALID", "Workflow calls need a JSON object as input.")
    if node.type == "for_each":
        items = _pointer(data, node.config["source"])
        if not isinstance(items, list) or len(items) > node.config["max_items"]:
            fail(
                422,
                "LOOP_ITEM_LIMIT",
                "The loop input must be a list within its configured item limit; nothing was truncated.",
            )
        values = [
            ({"item": item, "index": index} if node.config["input_mode"] == "envelope" else item)
            for index, item in enumerate(items)
        ]
    else:
        values = [data]
    # Check every item before running the first one: malformed later input must
    # not cause avoidable partial actions. Output failures can still be partial.
    for value in values:
        if not isinstance(value, dict) or example_errors(graph.input_schema, value, "input"):
            fail(
                422,
                "SUBWORKFLOW_INPUT_INVALID",
                "Every child input must be an object matching the published workflow contract.",
            )
        bounded_json(value, max_bytes=65536)
    return values


def preview_handler(db, workspace_id, raw_catalog, deadline, ancestry=(), depth=0):
    """Compose only local child workflows, with one shared wall-clock deadline."""
    from app.modules.workflows.preview import run_preview, validation

    def call(node, data):
        version, graph = resolve_version(db, workspace_id, node.config)
        if depth + 1 >= MAX_CALL_DEPTH or version.workflow_id in ancestry:
            fail(
                422,
                "SUBWORKFLOW_RECURSION",
                "This workflow call exceeds the supported nesting rules.",
            )
        checked = validation(
            db, workspace_id, graph, raw_catalog, root_workflow_id=version.workflow_id
        )
        if not checked["publishable"] or checked["has_external"] or checked["has_pause"]:
            fail(
                422,
                "PREVIEW_UNSUPPORTED",
                "Child workflows with external steps need a published run.",
            )
        multiplier = node.config["max_items"] if node.type == "for_each" else 1
        if 1 + multiplier * checked["expanded_steps"] > MAX_EXPANDED_STEPS:
            fail(
                422,
                "WORKFLOW_EXPANSION_LIMIT",
                "This isolated step exceeds the 120-step expanded-work limit.",
            )
        values = inputs_for(node, data, graph)
        node_deadline = min(deadline, time.monotonic() + node.policy.get("timeout_seconds", 60))
        outputs = []
        for value in values:
            remaining = min(
                node_deadline - time.monotonic(), graph.limits.get("timeout_seconds", 60)
            )
            if remaining <= 0:
                fail(408, "PREVIEW_TIMEOUT", "This workflow call exceeded its shared deadline.")
            child_deadline = time.monotonic() + remaining
            result = run_preview(
                db,
                workspace_id,
                graph,
                value,
                mcp_catalog_json=raw_catalog,
                max_seconds=remaining,
                composition_handler=preview_handler(
                    db,
                    workspace_id,
                    raw_catalog,
                    child_deadline,
                    (*ancestry, version.workflow_id),
                    depth + 1,
                ),
                root_workflow_id=version.workflow_id,
            )
            outputs.append(result["output"])
            bounded_json(outputs, max_bytes=65000)
        return {"items": outputs, "count": len(outputs)} if node.type == "for_each" else outputs[0]

    return call
