"""Published workflows offered to a model as tools.

A tool workflow must be safe to start from inside a model's tool loop: published in this
workspace, free of agent or LLM steps (no model recursion) and free of approvals or timers (the
loop cannot pause). Publishing pins each workflow's graph hash and input contract.
"""

import re
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.errors import fail

# Each model run may start at most this many workflows, which also bounds expanded work.
MAX_WORKFLOW_TOOL_CALLS = 3


def alias(grant: dict) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", grant.get("name", "").lower()).strip("_")[:40] or "workflow"
    return f"run_{base}_{grant['version_id'].replace('-', '')[:8]}"


def inspect(db: Session, workspace_id: uuid.UUID, grant: dict, raw_catalog: str = "[]", root_workflow_id=None) -> tuple:
    """Resolve a granted version and check it can run as a tool. Returns (version, graph, checked)."""
    from app.modules.workflows.composition import resolve_version
    from app.modules.workflows.preview import validation

    version, graph = resolve_version(db, workspace_id, grant)
    if root_workflow_id is not None and version.workflow_id == root_workflow_id:
        fail(422, "WORKFLOW_TOOL_RECURSION", "A workflow cannot offer itself as a tool.")
    checked = validation(db, workspace_id, graph, raw_catalog, root_workflow_id=version.workflow_id)
    if not checked["publishable"]:
        fail(422, "WORKFLOW_TOOL_INVALID", f"{version.name} v{version.number} can no longer run.")
    if checked["agent_steps"] or checked["has_pause"]:
        fail(422, "WORKFLOW_TOOL_UNSUPPORTED", f"{version.name} v{version.number} has agent, LLM, approval or timer steps, so it cannot run as a tool.")
    return version, graph, checked


def pin(db: Session, workspace_id: uuid.UUID, grants: list[dict], raw_catalog: str = "[]") -> list[dict]:
    pinned = []
    for grant in grants:
        version, graph, checked = inspect(db, workspace_id, {"version_id": grant["version_id"]}, raw_catalog)
        pinned.append({
            "version_id": str(version.id),
            "name": grant.get("name") or version.name,
            "description": grant.get("description", ""),
            "input_schema": graph.input_schema,
            "graph_hash": version.graph_hash,
            "has_external": checked["has_external"],
        })
    return pinned


def expansion(db: Session, workspace_id: uuid.UUID, grants: list[dict], raw_catalog: str = "[]") -> int:
    """Worst-case expanded steps a model run adds by starting tool workflows."""
    widest = 0
    for grant in grants:
        try:
            widest = max(widest, inspect(db, workspace_id, grant, raw_catalog)[2]["expanded_steps"])
        except HTTPException:
            continue
    return widest * MAX_WORKFLOW_TOOL_CALLS
