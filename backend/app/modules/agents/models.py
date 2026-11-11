import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Agent(Base):
    __tablename__ = "agent"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint("revision >= 1", name="positive_revision"),
        CheckConstraint("(workflow_id IS NULL) = (node_id IS NULL)", name="workflow_node_pair"),
        CheckConstraint("workflow_id IS NULL OR playground_for IS NULL", name="one_owner"),
        CheckConstraint("system_role IS NULL OR (workflow_id IS NULL AND playground_for IS NULL)", name="system_role_alone"),
        Index(
            "ix_agent_workspace_updated", "workspace_id", text("updated_at DESC"), text("id DESC")
        ),
        Index(
            "uq_agent_workflow_node", "workflow_id", "node_id", unique=True,
            postgresql_where=text("workflow_id IS NOT NULL"),
        ),
        Index(
            "uq_agent_playground_for", "playground_for", unique=True,
            postgresql_where=text("playground_for IS NOT NULL"),
        ),
        Index(
            "uq_agent_system_role", "workspace_id", "system_role", unique=True,
            postgresql_where=text("system_role IS NOT NULL"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    revision: Mapped[int] = mapped_column(default=1)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set only for the hidden agent behind a workflow LLM step; such agents never appear as drafts.
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflow.id"), nullable=True)
    node_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Set only for the hidden twin that runs an agent's unsaved draft in the builder's live chat.
    playground_for: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent.id"), nullable=True)
    # Set only for hidden system agents, such as the builder's AI helpers ("assist:improve").
    system_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentVersion(Base):
    __tablename__ = "agent_version"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "agent_id"], ["agent.workspace_id", "agent.id"]),
        ForeignKeyConstraint(
            ["workspace_id", "connection_id"],
            ["integration_connection.workspace_id", "integration_connection.id"],
        ),
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("agent_id", "number", name="uq_agent_version_number"),
        UniqueConstraint(
            "agent_id", "source_revision", "purpose", name="uq_agent_version_source_purpose"
        ),
        CheckConstraint("number >= 1 AND source_revision >= 1", name="positive_version"),
        CheckConstraint("purpose IN ('test','published')", name="valid_purpose"),
        CheckConstraint(
            "purpose != 'published' OR (connection_id IS NOT NULL AND credential_generation IS NOT NULL)",
            name="published_connection",
        ),
        Index("ix_agent_version_history", "workspace_id", "agent_id", text("number DESC")),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column()
    agent_id: Mapped[uuid.UUID] = mapped_column()
    connection_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    credential_generation: Mapped[int | None] = mapped_column(nullable=True)
    number: Mapped[int] = mapped_column()
    purpose: Mapped[str] = mapped_column(String(20))
    source_revision: Mapped[int] = mapped_column()
    schema_version: Mapped[int] = mapped_column(default=1)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500))
    config: Mapped[dict] = mapped_column(JSONB)
    config_hash: Mapped[str] = mapped_column(String(64))
    change_summary: Mapped[str] = mapped_column(String(1000))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def user_built():
    """Filter for agents people build, excluding hidden LLM-step, playground and system agents."""
    from sqlalchemy import and_

    return and_(Agent.workflow_id.is_(None), Agent.playground_for.is_(None), Agent.system_role.is_(None))


def standalone_versions():
    """Filter for versions of user-built agents."""
    from sqlalchemy import select

    return AgentVersion.agent_id.in_(select(Agent.id).where(user_built()))


class ConversationTurn(Base):
    """One encrypted message of an agent's remembered conversation, keyed by a hashed conversation ID."""

    __tablename__ = "conversation_turn"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "agent_id"], ["agent.workspace_id", "agent.id"]),
        UniqueConstraint("conversation_hash", "sequence", name="uq_conversation_turn_sequence"),
        CheckConstraint("role IN ('user','assistant')", name="valid_role"),
        CheckConstraint("sequence >= 1", name="positive_sequence"),
        Index("ix_conversation_turn_recent", "conversation_hash", text("sequence DESC")),
        Index("ix_conversation_turn_expiry", "expires_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column()
    agent_id: Mapped[uuid.UUID] = mapped_column()
    conversation_hash: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column()
    role: Mapped[str] = mapped_column(String(10))
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
