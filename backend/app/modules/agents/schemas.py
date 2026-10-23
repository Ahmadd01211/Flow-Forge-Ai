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


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)
    schema_version: int = Field(default=1, ge=1, le=1)
    instructions: str = Field(default="", max_length=32000)
    provider: Literal["openai", "openrouter", "anthropic", "gemini", "deepseek"] = "openai"
    model_id: str = Field(default="", max_length=200)
    tool_keys: list[Literal["json.extract", "text.replace"]] = Field(
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
    section: Literal["instructions", "model", "schemas", "limits"]


class ReadinessRead(BaseModel):
    revision: int
    publishable: bool
    runnable: bool
    errors: list[ReadinessIssue]
    warnings: list[ReadinessIssue]
    max_output_tokens: int
    model_called: Literal[False] = False
