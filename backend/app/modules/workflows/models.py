import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Workflow(Base):
    __tablename__ = "workflow"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint("revision >= 1", name="positive_revision"),
        Index(
            "ix_workflow_workspace_updated",
            "workspace_id",
            text("updated_at DESC"),
            text("id DESC"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")
    graph: Mapped[dict] = mapped_column(JSONB)
    revision: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkflowVersion(Base):
    __tablename__ = "workflow_version"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workflow_id", "number", name="uq_workflow_version_number"),
        UniqueConstraint("workflow_id", "source_revision", name="uq_workflow_version_revision"),
        ForeignKeyConstraint(
            ["workspace_id", "workflow_id"], ["workflow.workspace_id", "workflow.id"]
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    workflow_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    graph: Mapped[dict] = mapped_column(JSONB, nullable=False)
    graph_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkflowRun(Base):
    __tablename__ = "workflow_run"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint(
            "workspace_id",
            "requested_by",
            "idempotency_key_hash",
            name="uq_workflow_run_idempotency",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "version_id"], ["workflow_version.workspace_id", "workflow_version.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "deployment_id"],
            ["deployment.workspace_id", "deployment.id"],
            name="fk_workflow_run_deployment",
        ),
        CheckConstraint(
            "state IN ('queued','running','waiting','completed','failed','cancelled')",
            name="valid_workflow_run_state",
        ),
        Index("ix_workflow_run_dispatch", "state", "last_dispatched_at"),
        Index("ix_workflow_run_history", "workspace_id", text("created_at DESC")),
        Index("ix_workflow_run_deployment", "deployment_id", "created_at"),
        ForeignKeyConstraint(
            ["workspace_id", "automation_id"],
            ["workflow_automation.workspace_id", "workflow_automation.id"],
            name="fk_workflow_run_automation",
        ),
        Index("ix_workflow_run_automation", "automation_id", "created_at"),
        Index("ix_workflow_run_active_workspace", "workspace_id", postgresql_where=text("state IN ('queued','running','waiting')")),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    version_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    automation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    input_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    input_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    output_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    output_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_inflight: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 8), nullable=True)
    reserved_max_usd: Mapped[Decimal] = mapped_column(Numeric(14, 8), default=Decimal("0"), server_default="0")
    uncertain_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 8), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claim_token: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowCheckpoint(Base):
    __tablename__ = "workflow_checkpoint"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "run_id"], ["workflow_run.workspace_id", "workflow_run.id"]),
        UniqueConstraint("run_id", "node_id", name="uq_workflow_checkpoint_node"),
        UniqueConstraint("run_id", "sequence", name="uq_workflow_checkpoint_sequence"),
        CheckConstraint("state IN ('running','waiting','completed','skipped','failed')", name="checkpoint_state"),
        CheckConstraint("attempt >= 1 AND sequence >= 0 AND sequence < 120", name="checkpoint_bounds"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    node_id: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(20))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    error_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowPause(Base):
    """A durable timer or decision bound to a run's encrypted checkpoint input."""

    __tablename__ = "workflow_pause"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "run_id"], ["workflow_run.workspace_id", "workflow_run.id"]),
        UniqueConstraint("run_id", "node_id", name="uq_workflow_pause_node"),
        CheckConstraint("kind IN ('approval','wait')", name="pause_kind"),
        CheckConstraint("state IN ('pending','approved','rejected','elapsed','expired','cancelled')", name="pause_state"),
        Index("ix_workflow_pause_due", "state", "due_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    node_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(20), default="pending")
    prompt: Mapped[str] = mapped_column(String(500), default="")
    allow_requester: Mapped[bool] = mapped_column(Boolean, default=False)
    input_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
