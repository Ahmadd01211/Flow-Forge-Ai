import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, computed_field, field_validator

from app.providers.profiles import ModelCapability, capability
from app.providers.registry import Provider


class ProviderCredential(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr = Field(min_length=1, max_length=2048)

    @field_validator("api_key")
    @classmethod
    def key_format(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if any(char.isspace() for char in secret):
            raise ValueError("The credential must not contain whitespace")
        return value


class DefaultModelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=200)


class ConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    provider: Provider
    display_name: str
    state: Literal["active", "revoked"]
    credential_generation: int
    masked_hint: str
    verified_models: list[str]
    default_model_id: str | None
    verified_at: datetime
    revoked_at: datetime | None

    @computed_field
    @property
    def model_capabilities(self) -> dict[str, ModelCapability]:
        return {model: capability(self.provider, model) for model in self.verified_models}


class ConnectionList(BaseModel):
    items: list[ConnectionRead]
