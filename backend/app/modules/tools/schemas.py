from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolInvoke(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: dict = Field(default_factory=dict)


class ToolResult(BaseModel):
    output: dict[str, Any]
