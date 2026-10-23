import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
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
        Index(
            "ix_agent_workspace_updated", "workspace_id", text("updated_at DESC"), text("id DESC")
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    revision: Mapped[int] = mapped_column(default=1)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
