import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: uuid.UUID
    input: dict[str, Any]


class RunRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    version_id: uuid.UUID
    state: Literal["queued", "running", "completed", "failed", "cancelled"]
    output: dict[str, Any] | None
    error_code: str | None
    cancel_requested: bool
    model_started: bool
    reserved_max_usd: str
    cost_usd: str | None
    uncertain_cost_usd: str | None
    input_tokens: int | None
    output_tokens: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RunList(BaseModel):
    items: list[RunRead]


class RunEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    sequence: int
    kind: str
    status: str
    tool_key: str | None
    input_tokens: int | None
    output_tokens: int | None
    error_code: str | None
    created_at: datetime


class RunEventList(BaseModel):
    items: list[RunEventRead]
