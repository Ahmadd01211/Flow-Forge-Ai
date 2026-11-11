import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float = Field(ge=-100000, le=100000, allow_inf_nan=False)
    y: float = Field(ge=-100000, le=100000, allow_inf_nan=False)


class WorkflowStepRead(BaseModel):
    node_id: str
    type: str
    status: Literal["running", "waiting", "completed", "skipped", "failed"]
    output: Any
    usage: dict | None = None
    selected_port: str | None = None
    error_code: str | None = None
    attempt: int = 1
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    definition_node_id: str | None = None
    scope: list[str] = Field(default_factory=list)
    parent_node_id: str | None = None
    iteration_index: int | None = None
    workflow_version_id: uuid.UUID | None = None


class WorkflowStepDetail(WorkflowStepRead):
    input: Any


class WorkflowPauseRead(BaseModel):
    id: uuid.UUID
    node_id: str
    kind: Literal["approval", "wait"]
    state: Literal["pending", "approved", "rejected", "elapsed", "expired", "cancelled"]
    prompt: str
    allow_requester: bool
    created_at: datetime
    due_at: datetime
    decided_by: uuid.UUID | None
    settled_at: datetime | None


class WorkflowRunRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    version_id: uuid.UUID
    automation_id: uuid.UUID | None
    deployment_id: uuid.UUID | None
    source: Literal["manual", "chat", "webhook", "schedule", "deployment", "replay"] = "manual"
    state: Literal["queued", "running", "waiting", "completed", "failed", "cancelled"]
    requested_by: uuid.UUID
    pauses: list[WorkflowPauseRead] = Field(default_factory=list)
    output: Any
    steps: list[WorkflowStepRead] | None
    error_code: str | None
    reserved_max_usd: str
    cost_usd: str | None
    uncertain_cost_usd: str | None
    input_tokens: int | None
    output_tokens: int | None
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class WorkflowRunList(BaseModel):
    items: list[WorkflowRunRead]


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    type: Literal["manual_input", "webhook_trigger", "schedule_trigger", "chat_trigger", "agent", "llm", "tool", "mcp_tool", "http_tool", "subworkflow", "for_each", "approval", "wait", "condition", "merge", "transform", "text_template", "list_filter", "json_parse", "result"]
    label: str = Field(min_length=1, max_length=100)
    position: Position
    join: Literal["all", "active"] = "all"
    config: dict = Field(default_factory=dict)
    policy: dict = Field(default_factory=lambda: {"timeout_seconds": 60, "max_attempts": 1})


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    source: str
    source_port: Literal["out", "true", "false"] = "out"
    target: str
    target_port: Literal["in"] = "in"
    mappings: list[dict] = Field(default_factory=list, max_length=64)


class Graph(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    nodes: list[Node] = Field(max_length=100)
    edges: list[Edge] = Field(max_length=200)
    input_schema: dict = Field(default_factory=lambda: {"type": "object"})
    output_schema: dict = Field(default_factory=lambda: {"type": "object"})
    limits: dict = Field(
        default_factory=lambda: {
            "timeout_seconds": 60,
            "max_cost_usd": "0.10",
            "max_parallel_steps": 2,
        }
    )


def initial_graph() -> dict:
    return Graph(
        nodes=[
            Node(
                id="input",
                type="manual_input",
                label="Manual input",
                position=Position(x=100, y=180),
            ),
            Node(
                id="result",
                type="result",
                label="Return result",
                position=Position(x=500, y=180),
                config={"value": {"kind": "output", "node_id": "input", "pointer": ""}},
            ),
        ],
        edges=[
            Edge(
                id="input-result",
                source="input",
                target="result",
                mappings=[{"from": "", "to": ""}],
            )
        ],
    ).model_dump()


class WorkflowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name is required")
        return value.strip()


class WorkflowUpdate(WorkflowCreate):
    expected_revision: int = Field(ge=1)
    graph: Graph


class ValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


class DraftCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    graph: Graph


class WorkflowCallOption(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    name: str
    number: int
    input_schema: dict
    output_schema: dict
    expanded_steps: int
    agent_steps: int
    has_external: bool
    has_pause: bool
    limits: dict


class WorkflowCallOptions(BaseModel):
    items: list[WorkflowCallOption]


class NodeTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    graph: Graph
    input: Any = Field(default_factory=dict)
    # Earlier steps' outputs by node ID, for result fields that read them.
    outputs: dict[str, Any] = Field(default_factory=dict, max_length=100)
    confirm_external: bool = False
