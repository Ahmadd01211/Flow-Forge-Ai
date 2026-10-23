from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class McpCredential(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bearer_token: SecretStr = Field(default=SecretStr(""), max_length=4096)


class McpToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    arguments: dict[str, Any] = Field(default_factory=dict)
