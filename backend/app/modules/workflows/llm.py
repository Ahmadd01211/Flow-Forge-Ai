"""Inline LLM steps: settings live on the workflow node; publishing freezes them into a hidden agent.

The hidden agent reuses agent validation, tool-grant pinning, credential checks, budgets and the
agent runtime, so a published LLM step runs exactly like an agent step.
"""

import uuid

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.agents.models import Agent, AgentVersion
from app.modules.agents.readiness import assess
from app.modules.agents.schemas import AgentConfig
from app.modules.executions.service import MODEL_PRICES
from app.modules.integrations.service import get_connection

AGENT_KEYS = ("instructions", "provider", "model_id", "tool_keys", "mcp_tools", "http_tools", "output_schema", "limits", "memory", "workflow_tools", "skills")
DEFAULT_OUTPUT = {
    "type": "object",
    "properties": {"reply": {"type": "string"}},
    "required": ["reply"],
    "additionalProperties": False,
}
# The step receives whatever object arrives on its connection.
OPEN_INPUT = {"type": "object"}
SECTION_PATHS = {
    "instructions": "config.instructions",
    "model": "config.model_id",
    "schemas": "config.output_schema",
    "limits": "config.limits",
}


def agent_config(config: dict) -> dict:
    raw = {key: config[key] for key in AGENT_KEYS if key in config}
    raw.setdefault("output_schema", DEFAULT_OUTPUT)
    return AgentConfig.model_validate({**raw, "input_schema": OPEN_INPUT}).model_dump()


def issues(db: Session, workspace_id: uuid.UUID, node, raw_catalog: str) -> tuple[list[dict], list[dict]]:
    """Readiness of a draft LLM step, reported against the inspector fields."""

    def issue(item: dict) -> dict:
        path = SECTION_PATHS.get(item.get("section"), "config")
        return {"code": item["code"], "message": item["message"], "node_id": node.id, "edge_id": None, "path": path}

    try:
        config = agent_config(node.config)
    except ValidationError:
        return [issue({"code": "NODE_CONFIG_INVALID", "message": "These LLM settings are not valid."})], []
    checked = assess(db, workspace_id, config, get_connection(db, workspace_id, config["provider"]), raw_catalog)
    errors = [issue(item) for item in checked["errors"]]
    if not errors and (config["provider"], config["model_id"]) not in MODEL_PRICES:
        errors.append(issue({"code": "RUNTIME_UNSUPPORTED", "message": "This model is setup only and cannot run in a workflow yet.", "section": "model"}))
    warnings = [issue(item) for item in checked["warnings"] if item["code"] != "RUNTIME_UNSUPPORTED"]
    return errors, warnings


def freeze(db: Session, workspace_id: uuid.UUID, workflow_id: uuid.UUID, node, actor_id: uuid.UUID, raw_catalog: str) -> AgentVersion:
    """Publish the step's current settings as its hidden agent's version, reusing an identical one."""
    from app.modules.agents.managed import freeze as freeze_agent

    config = agent_config(node.config)
    agent = db.scalar(
        select(Agent).where(Agent.workflow_id == workflow_id, Agent.node_id == node.id).with_for_update()
    )
    if not agent:
        agent = Agent(
            workspace_id=workspace_id, workflow_id=workflow_id, node_id=node.id, name=node.label[:100],
            description="Managed by a workflow LLM step.", config=config,
        )
        db.add(agent)
        db.flush()
    return freeze_agent(db, workspace_id, agent, config, node.label, actor_id, raw_catalog, f"Published from workflow step {node.id}.")
