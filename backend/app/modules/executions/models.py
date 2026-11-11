import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AgentRun(Base):
    __tablename__ = "agent_run"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint(
            "workspace_id", "requested_by", "idempotency_key_hash", name="uq_agent_run_idempotency"
        ),
        ForeignKeyConstraint(
            ["workspace_id", "version_id"], ["agent_version.workspace_id", "agent_version.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "deployment_id"],
            ["deployment.workspace_id", "deployment.id"],
            name="fk_agent_run_deployment",
        ),
        CheckConstraint(
            "state IN ('queued','running','waiting','completed','failed','cancelled')",
            name="valid_agent_run_state",
        ),
        Index("ix_agent_run_history", "workspace_id", text("created_at DESC"), text("id DESC")),
        Index("ix_agent_run_dispatch", "state", "last_dispatched_at"),
        Index("ix_agent_run_deployment", "deployment_id", "created_at"),
        Index("ix_agent_run_active_workspace", "workspace_id", postgresql_where=text("state IN ('queued','running','waiting')")),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace.id"))
    version_id: Mapped[uuid.UUID] = mapped_column()
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    idempotency_key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20))
    input_nonce: Mapped[bytes] = mapped_column(LargeBinary)
    input_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    output_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    output_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    claim_token: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    model_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    max_output_tokens: Mapped[int] = mapped_column(Integer)
    reserved_max_usd: Mapped[Decimal] = mapped_column(Numeric(12, 8))
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    uncertain_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RunEvent(Base):
    __tablename__ = "agent_run_event"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "run_id"], ["agent_run.workspace_id", "agent_run.id"]
        ),
        UniqueConstraint("run_id", "sequence"),
        Index("ix_agent_run_event_run", "workspace_id", "run_id", "sequence"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    tool_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Encrypted {"arguments", "output"} of a tool step, for the run trace.
    nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class AgentToolApproval(Base):
    """One encrypted, independent decision for one exact agent MCP call."""

    __tablename__ = "agent_tool_approval"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "run_id"], ["agent_run.workspace_id", "agent_run.id"]
        ),
        CheckConstraint(
            "state IN ('pending','approved','rejected','expired','cancelled','claimed','ready','resuming','uncertain','completed')",
            name="valid_agent_tool_approval_state",
        ),
        Index("ix_agent_tool_approval_pending", "expires_at", postgresql_where=text("state = 'pending'")),
        Index(
            "uq_agent_tool_approval_active_run",
            "run_id",
            unique=True,
            postgresql_where=text("state IN ('pending','approved','claimed','ready','resuming','uncertain')"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    tool_key: Mapped[str] = mapped_column(String(80), nullable=False)
    server_id: Mapped[str] = mapped_column(String(40), nullable=False)
    server_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_description: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    read_only: Mapped[bool] = mapped_column(nullable=False, default=False)
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    call_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RunFeedback(Base):
    """One person's thumbs up or down on an agent run, with an optional comment."""

    __tablename__ = "agent_run_feedback"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "run_id"], ["agent_run.workspace_id", "agent_run.id"]),
        UniqueConstraint("run_id", "created_by", name="uq_agent_run_feedback_author"),
        CheckConstraint("rating IN ('up','down')", name="valid_rating"),
        Index("ix_agent_run_feedback_run", "workspace_id", "run_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    rating: Mapped[str] = mapped_column(String(10), nullable=False)
    comment: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
