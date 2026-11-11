import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class HttpToolCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    url: str = Field(min_length=8, max_length=2048)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    read_only: bool = Field(default=False, strict=True)
    auth_mode: Literal["none", "bearer", "api_key"] = "none"
    auth_header: str = Field(default="X-API-Key", max_length=64)
    credential: SecretStr | None = None
    input_schema: dict = Field(default_factory=lambda: {"type": "object"})
    output_schema: dict = Field(default_factory=lambda: {"type": "object"})
    confirm_permissions: bool = Field(default=False, strict=True)


class HttpToolRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    url: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    read_only: bool
    auth_mode: Literal["none", "bearer", "api_key"]
    auth_header: str
    credential_present: bool
    input_schema: dict
    output_schema: dict
    spec_hash: str
    generation: int
    state: Literal["active", "revoked"]
    created_at: datetime


class HttpToolList(BaseModel):
    items: list[HttpToolRead]


class HttpCredentialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_generation: int = Field(ge=1, strict=True)
    credential: SecretStr | None = None


class HttpGeneration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_generation: int = Field(ge=1, strict=True)


class HttpToolTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: dict
    confirm_external: bool = Field(default=False, strict=True)
