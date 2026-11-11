"""AI helpers for the agent builder: improve instructions, draft an agent, suggest test inputs.

Each task is a hidden system agent ("assist:<task>") frozen with the workspace's chosen model, so a
helper call is an ordinary agent run: same budgets, daily limits, usage and trace as any other.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.agents.managed import freeze
from app.modules.agents.models import Agent, AgentVersion
from app.modules.agents.schemas import AgentConfig

TEXT = {"type": "string"}
LIST = {"type": "array", "items": {"type": "string"}}

TASKS: dict[str, dict] = {
    "improve": {
        "name": "Builder assistant: improve instructions",
        "instructions": (
            "You are an expert prompt engineer helping someone configure an AI agent in FlowForge.\n"
            "Rewrite the agent's instructions so they are clear, specific and well structured:\n"
            "- state the agent's role and goal in one or two sentences;\n"
            "- describe what it should do, step by step;\n"
            "- say when to use each of its tools and skills (only those listed);\n"
            "- say what to do when information is missing or a request is out of scope;\n"
            "- list anything it must never do.\n"
            "Keep every fact, policy and constraint from the original. Never invent business rules, product details or tools.\n"
            "Use plain language and short bullet points, under 400 words. Keep the original language.\n"
            "Return the improved instructions and up to five short notes saying what you changed and why."
        ),
        "output": {"instructions": TEXT, "changes": LIST},
    },
    "draft": {
        "name": "Builder assistant: draft an agent",
        "instructions": (
            "You help people set up an AI agent in FlowForge from a plain-language description.\n"
            "Produce a starting configuration:\n"
            "- name: short, at most 40 characters;\n"
            "- description: one sentence saying what the agent is for;\n"
            "- instructions: role, steps, when to use tools and skills, when to ask a clarifying question, and limits; under 300 words;\n"
            "- preset: \"chat\" for conversations, \"classify\" for sorting text into labels, \"extract\" for pulling fields out of text;\n"
            "- labels: for classify, 2-6 label values in snake_case, otherwise empty;\n"
            "- fields: for extract, 2-8 field names in snake_case, otherwise empty;\n"
            "- memory: true only when it should remember earlier messages of a conversation;\n"
            "- tool_ids and skill_ids: only ids from the offered lists that clearly fit; empty when none fit.\n"
            "Never invent tools, skills or business facts."
        ),
        "output": {
            "name": TEXT, "description": TEXT, "instructions": TEXT,
            "preset": {"type": "string", "enum": ["chat", "classify", "extract"]},
            "labels": LIST, "fields": LIST, "memory": {"type": "boolean"}, "tool_ids": LIST, "skill_ids": LIST,
        },
    },
    "examples": {
        "name": "Builder assistant: suggest test inputs",
        "instructions": (
            "Write realistic test inputs so someone can check how their AI agent behaves.\n"
            "Return five examples: three typical requests and two tricky ones (missing information, an out-of-scope request, or ambiguous wording).\n"
            "Each input_json must be a JSON object, serialised as a string, that matches the given input schema exactly.\n"
            "Give each example a short label such as \"Typical return\" or \"Missing order number\"."
        ),
        "output": {"examples": {"type": "array", "items": {"type": "object", "properties": {"label": TEXT, "input_json": TEXT}, "required": ["label", "input_json"], "additionalProperties": False}}},
    },
}


def _config(task: str, provider: str, model_id: str) -> dict:
    spec = TASKS[task]
    return AgentConfig.model_validate({
        "instructions": spec["instructions"],
        "provider": provider,
        "model_id": model_id,
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object", "properties": spec["output"], "required": list(spec["output"]), "additionalProperties": False},
        "limits": {"max_iterations": 1, "timeout_seconds": 45, "max_cost_usd": "0.05", "max_tool_calls": 0, "max_output_tokens": 2048},
    }).model_dump()


def assistant_version(db: Session, workspace_id: uuid.UUID, task: str, provider: str, model_id: str, actor_id: uuid.UUID, raw_catalog: str) -> AgentVersion:
    """Freeze the task's hidden assistant with this model, reusing the version while nothing changes."""
    role = f"assist:{task}"
    config = _config(task, provider, model_id)
    agent = db.scalar(select(Agent).where(Agent.workspace_id == workspace_id, Agent.system_role == role).with_for_update())
    if not agent:
        agent = Agent(workspace_id=workspace_id, system_role=role, name=TASKS[task]["name"], description="Powers the agent builder's AI helpers.", config=config)
        db.add(agent)
        db.flush()
    return freeze(db, workspace_id, agent, config, TASKS[task]["name"], actor_id, raw_catalog, "Builder assistant.")
