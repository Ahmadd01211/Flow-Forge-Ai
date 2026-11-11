import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Limits(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_default=True, json_schema_serialization_defaults_required=True
    )
    max_iterations: int = Field(default=8, ge=1, le=20)
    timeout_seconds: int = Field(default=60, ge=1, le=300)
    max_cost_usd: str = Field(default="0.10", pattern=r"^(0|[1-9][0-9]{0,3})(\.[0-9]{1,8})?$")
    max_tool_calls: int = Field(default=8, ge=0, le=32)
    max_output_tokens: int = Field(default=4096, ge=16, le=4096)

    @field_validator("max_cost_usd")
    @classmethod
    def canonical_money(cls, value: str) -> str:
        return format(Decimal(value).normalize(), "f")


class McpGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    tool_name: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,80}$")
    connection_generation: int | None = Field(default=None, ge=1)
    input_schema_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    input_schema: dict = Field(default_factory=dict)
    description: str = Field(default="", max_length=500)


class HttpGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_id: str = Field(pattern=r"^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$")
    connection_generation: int | None = Field(default=None, ge=1)
    spec_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    input_schema: dict = Field(default_factory=dict)
    name: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=500)


class WorkflowGrant(BaseModel):
    """A published workflow the model may start as a tool; publishing pins its contract."""

    model_config = ConfigDict(extra="forbid")
    version_id: str = Field(pattern=r"^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$")
    name: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=500)
    input_schema: dict = Field(default_factory=dict)
    graph_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    has_external: bool | None = None


class SkillExample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: str = Field(max_length=2000)
    output: str = Field(max_length=2000)


class SkillGrant(BaseModel):
    """A skill attached to an agent. Drafts name the skill; publishing pins its version and text."""

    model_config = ConfigDict(extra="forbid")
    skill_id: str = Field(pattern=r"^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$")
    name: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=300)
    version_id: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$")
    number: int | None = Field(default=None, ge=1)
    instructions: str = Field(default="", max_length=8000)
    examples: list[SkillExample] = Field(default_factory=list, max_length=5)


class Memory(BaseModel):
    """Remember earlier turns of a conversation identified by a field in each run's input."""

    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)
    key_pointer: str = Field(default="/conversation_id", max_length=200, pattern=r"^(/[^/]*)+$")
    max_turns: int = Field(default=10, ge=1, le=20)
    retention_days: int = Field(default=30, ge=1, le=90)

    @field_validator("key_pointer")
    @classmethod
    def safe_pointer(cls, value: str) -> str:
        if any(part in {"__proto__", "constructor", "prototype"} for part in value.split("/")[1:]):
            raise ValueError("This field name is not supported.")
        return value


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)
    schema_version: int = Field(default=1, ge=1, le=1)
    instructions: str = Field(default="", max_length=32000)
    provider: Literal["openai", "openrouter", "anthropic", "gemini", "deepseek"] = "openai"
    model_id: str = Field(default="", max_length=200)
    tool_keys: list[Literal["json.extract", "text.replace", "demo.order_lookup"]] = Field(
        default_factory=list, max_length=8
    )
    input_schema: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {"ticket": {"type": "string"}},
            "required": ["ticket"],
            "additionalProperties": False,
        }
    )
    output_schema: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {"priority": {"type": "string", "enum": ["urgent", "normal"]}},
            "required": ["priority"],
            "additionalProperties": False,
        }
    )
    limits: Limits = Field(default_factory=Limits)
    mcp_tools: list[McpGrant] = Field(default_factory=list, max_length=8)
    http_tools: list[HttpGrant] = Field(default_factory=list, max_length=8)
    memory: Memory | None = None
    workflow_tools: list[WorkflowGrant] = Field(default_factory=list, max_length=4)
    skills: list[SkillGrant] = Field(default_factory=list, max_length=8)
    # Set at publish: models that can call tools load skills on demand, others get them inline.
    skill_loading: Literal["on_demand", "inline"] = "on_demand"

    @field_validator("http_tools")
    @classmethod
    def unique_http_grants(cls, value):
        if len({grant.tool_id.lower() for grant in value}) != len(value):
            raise ValueError("Select each HTTP tool once.")
        return value

    @field_validator("skills")
    @classmethod
    def unique_skills(cls, value):
        if len({grant.skill_id.lower() for grant in value}) != len(value):
            raise ValueError("Attach each skill once.")
        return value

    @field_validator("workflow_tools")
    @classmethod
    def unique_workflow_tools(cls, value):
        if len({grant.version_id.lower() for grant in value}) != len(value):
            raise ValueError("Offer each workflow version once.")
        return value

    @field_validator("mcp_tools")
    @classmethod
    def unique_mcp_tools(cls, value):
        if len({(g.server_id, g.tool_name) for g in value}) != len(value):
            raise ValueError("Each MCP tool can only be granted once")
        return value

    @field_validator("tool_keys")
    @classmethod
    def unique_tools(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Choose each tool only once")
        return value


class AgentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    config: AgentConfig = Field(default_factory=AgentConfig)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name is required")
        return value.strip()


class AgentUpdate(AgentCreate):
    expected_revision: int = Field(ge=1)


class SnapshotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    change_summary: str = Field(default="", max_length=1000)


class RestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    version_id: uuid.UUID


class AgentRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str
    config: AgentConfig
    revision: int
    updated_at: datetime


class VersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    agent_id: uuid.UUID
    connection_id: uuid.UUID | None
    credential_generation: int | None
    number: int
    purpose: Literal["test", "published"]
    source_revision: int
    schema_version: int
    name: str
    description: str
    config: AgentConfig
    config_hash: str
    change_summary: str
    created_by: uuid.UUID
    created_at: datetime


class VersionList(BaseModel):
    items: list[VersionRead]
    next_cursor: str | None


class ExampleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: Any
    output: Any = None


class ExampleError(BaseModel):
    path: str
    code: str
    message: str


class ExampleResult(BaseModel):
    version_id: uuid.UUID
    config_hash: str
    input_valid: bool
    output_valid: bool | None
    errors: list[ExampleError]
    scope: Literal["contract"] = "contract"
    model_called: Literal[False] = False


class ReadinessIssue(BaseModel):
    code: str
    message: str
    section: Literal["instructions", "model", "schemas", "limits", "skills"]


class ReadinessRead(BaseModel):
    revision: int
    publishable: bool
    runnable: bool
    errors: list[ReadinessIssue]
    warnings: list[ReadinessIssue]
    max_output_tokens: int
    model_called: Literal[False] = False
