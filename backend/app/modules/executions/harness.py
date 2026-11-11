"""Append-only, metadata-only trace for the bounded agent harness.

Callers hold a row lock on AgentRun before appending. Inputs, outputs, credentials,
model reasoning, and tool arguments never enter this event table.
"""

import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.executions.models import AgentRun, RunEvent


def append_event(
    db: Session,
    run: AgentRun,
    kind: str,
    status: str,
    *,
    tool_key: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    error_code: str | None = None,
    detail: dict | None = None,
    master: bytes | None = None,
) -> None:
    sequence = (
        db.scalar(select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run.id)) or 0
    ) + 1
    event_id = uuid.uuid4()
    nonce = ciphertext = None
    if detail is not None and master is not None:
        from app.core.credentials import encrypt_secret
        nonce, ciphertext = encrypt_secret(master, run.workspace_id, event_id, 1, json.dumps(detail, ensure_ascii=False))
    db.add(
        RunEvent(
            id=event_id,
            nonce=nonce,
            ciphertext=ciphertext,
            workspace_id=run.workspace_id,
            run_id=run.id,
            sequence=sequence,
            kind=kind,
            status=status,
            tool_key=tool_key,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error_code=error_code,
        )
    )
