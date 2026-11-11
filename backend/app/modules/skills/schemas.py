import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.agents.schemas import HttpGrant, McpGrant, SkillExample


class SkillConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)
    instructions: str = Field(default="", max_length=8000)
    examples: list[SkillExample] = Field(default_factory=list, max_length=5)
    tool_keys: list[str] = Field(default_factory=list, max_length=8)
    mcp_tools: list[McpGrant] = Field(default_factory=list, max_length=8)
    http_tools: list[HttpGrant] = Field(default_factory=list, max_length=8)


class SkillWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=300)
    config: SkillConfig = Field(default_factory=SkillConfig)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name is required")
        return value.strip()


class SkillUpdate(SkillWrite):
    expected_revision: int = Field(ge=1)


class SkillPublish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


class SkillVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    skill_id: uuid.UUID
    number: int
    source_revision: int
    name: str
    description: str
    config: SkillConfig
    created_at: datetime
