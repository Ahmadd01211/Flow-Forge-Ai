from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float = Field(ge=-100000, le=100000, allow_inf_nan=False)
    y: float = Field(ge=-100000, le=100000, allow_inf_nan=False)


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    type: Literal["manual_input", "webhook_trigger", "schedule_trigger", "agent", "tool", "mcp_tool", "condition", "transform", "text_template", "list_filter", "json_parse", "result"]
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
