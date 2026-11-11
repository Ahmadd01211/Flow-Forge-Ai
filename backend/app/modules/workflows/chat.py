"""Chat trigger: each message starts a run of the workflow's latest published version.

The run input is {conversation_id, message}. An LLM step with memory keyed on /conversation_id
(its default) carries the conversation across messages. External apps send the same input
through a workflow deployment.
"""

import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import fail
from app.modules.workflows.models import WorkflowVersion

CHAT_SAMPLE = {"conversation_id": "c-1", "message": "Hello"}
CHAT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "conversation_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "message": {"type": "string", "minLength": 1, "maxLength": 4000},
    },
    "required": ["conversation_id", "message"],
    "additionalProperties": False,
}


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str | None = Field(default=None, min_length=1, max_length=200, pattern=r"^\S+$")
    message: str = Field(min_length=1, max_length=4000)


def chat_version(db: Session, workspace_id: uuid.UUID, workflow_id: uuid.UUID) -> WorkflowVersion:
    version = db.scalar(
        select(WorkflowVersion)
        .where(WorkflowVersion.workspace_id == workspace_id, WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.number.desc())
        .limit(1)
    )
    if not version:
        fail(409, "CHAT_NOT_PUBLISHED", "Publish this workflow before chatting with it.")
    if not any(node["type"] == "chat_trigger" for node in version.graph["nodes"]):
        fail(409, "CHAT_TRIGGER_REQUIRED", "The latest published version does not start with a chat trigger.")
    return version
