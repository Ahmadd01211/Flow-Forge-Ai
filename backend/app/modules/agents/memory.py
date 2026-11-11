"""Conversation memory: earlier turns are encrypted at rest and sent to the model as `history`.

A run opts in through `config["memory"]`. Its conversation is identified by the input field at
`key_pointer` (for example a chat or customer ID); only a hash of that ID is stored.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.credentials import decrypt_secret, encrypt_secret
from app.core.errors import fail
from app.modules.agents.models import Agent, ConversationTurn

MAX_HISTORY_BYTES = 32000
TURN_GENERATION = 1


def conversation_key(config: dict, data: object) -> str | None:
    """The run's conversation ID, or None when this agent does not remember conversations."""
    memory = config.get("memory")
    if not memory:
        return None
    from app.modules.workflows.preview import _pointer

    try:
        value = _pointer(data, memory["key_pointer"])
    except Exception:
        value = None
    if isinstance(value, bool) or not isinstance(value, str | int) or not 1 <= len(str(value)) <= 200:
        fail(422, "MEMORY_KEY_MISSING", f"Memory needs a conversation ID of 1–200 characters at {memory['key_pointer']} in the input.")
    return str(value)


def _hash(agent_id: uuid.UUID, key: str) -> str:
    return hashlib.sha256(f"{agent_id}:{key}".encode()).hexdigest()


def history(db: Session, master: bytes, workspace_id: uuid.UUID, agent_id: uuid.UUID, key: str, max_turns: int) -> list[dict]:
    """Recent turns oldest first, dropping the oldest until they fit the history byte budget."""
    rows = db.scalars(
        select(ConversationTurn)
        .where(
            ConversationTurn.workspace_id == workspace_id,
            ConversationTurn.conversation_hash == _hash(agent_id, key),
            ConversationTurn.expires_at > datetime.now(UTC),
        )
        .order_by(ConversationTurn.sequence.desc())
        .limit(max_turns * 2)
    ).all()
    turns = [
        {"role": row.role, "content": json.loads(decrypt_secret(master, workspace_id, row.id, TURN_GENERATION, row.nonce, row.ciphertext))}
        for row in reversed(rows)
    ]
    while turns and len(json.dumps(turns, ensure_ascii=False).encode()) > MAX_HISTORY_BYTES:
        turns = turns[2:] if len(turns) > 1 else []
    return turns


def model_input(data: object, turns: list[dict]) -> dict:
    return {"history": turns, "input": data}


def remember(
    db: Session, master: bytes, workspace_id: uuid.UUID, agent_id: uuid.UUID, key: str,
    user: object, assistant: object, memory: dict,
) -> None:
    """Append one exchange and drop turns beyond the configured window. The caller commits."""
    digest = _hash(agent_id, key)
    # Serialise writers per agent so concurrent runs in one conversation never share a sequence.
    db.scalar(select(Agent.id).where(Agent.id == agent_id).with_for_update())
    last = db.scalar(select(func.max(ConversationTurn.sequence)).where(ConversationTurn.conversation_hash == digest)) or 0
    expires = datetime.now(UTC) + timedelta(days=memory["retention_days"])
    for offset, (role, content) in enumerate((("user", user), ("assistant", assistant)), start=1):
        turn_id = uuid.uuid4()
        nonce, ciphertext = encrypt_secret(master, workspace_id, turn_id, TURN_GENERATION, json.dumps(content, ensure_ascii=False))
        db.add(ConversationTurn(
            id=turn_id, workspace_id=workspace_id, agent_id=agent_id, conversation_hash=digest,
            sequence=last + offset, role=role, nonce=nonce, ciphertext=ciphertext, expires_at=expires,
        ))
    db.execute(delete(ConversationTurn).where(
        ConversationTurn.conversation_hash == digest,
        ConversationTurn.sequence <= last + 2 - memory["max_turns"] * 2,
    ))


def purge_expired(db: Session) -> int:
    result = db.execute(delete(ConversationTurn).where(ConversationTurn.expires_at <= datetime.now(UTC)))
    db.commit()
    return result.rowcount or 0
