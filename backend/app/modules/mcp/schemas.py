from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class McpCredential(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bearer_token: SecretStr = Field(default=SecretStr(""), max_length=4096)


class McpToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpServerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100, pattern=r"\S")
    url: str = Field(min_length=9, max_length=2048)
    bearer_token: SecretStr = Field(default=SecretStr(""), max_length=4096)


class McpToolPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy: Literal["allow", "block"]
