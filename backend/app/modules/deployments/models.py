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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Deployment(Base):
    __tablename__ = "deployment"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "agent_version_id"], ["agent_version.workspace_id", "agent_version.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "workflow_version_id"],
            ["workflow_version.workspace_id", "workflow_version.id"],
        ),
        CheckConstraint(
            "(kind = 'agent' AND agent_version_id IS NOT NULL AND workflow_version_id IS NULL) OR (kind = 'workflow' AND workflow_version_id IS NOT NULL AND agent_version_id IS NULL)",
            name="valid_deployment_target",
        ),
        CheckConstraint("state IN ('active','revoked')", name="valid_deployment_state"),
        Index("ix_deployment_workspace", "workspace_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    agent_version_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    workflow_version_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


