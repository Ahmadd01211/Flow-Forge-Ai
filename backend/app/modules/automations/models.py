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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# A schedule has exactly one cadence: a bounded interval, or a cron expression with its timezone.
BINDING = (
    "(kind='webhook' AND key_hash IS NOT NULL AND interval_seconds IS NULL"
    " AND cron_expression IS NULL AND timezone IS NULL AND input_ciphertext IS NULL"
    " AND next_due_at IS NULL)"
    " OR (kind='schedule' AND key_hash IS NULL AND input_nonce IS NOT NULL"
    " AND input_ciphertext IS NOT NULL AND next_due_at IS NOT NULL AND ("
    "(interval_seconds IS NOT NULL AND interval_seconds BETWEEN 60 AND 86400"
    " AND cron_expression IS NULL AND timezone IS NULL)"
    " OR (interval_seconds IS NULL AND cron_expression IS NOT NULL AND timezone IS NOT NULL)))"
)


class WorkflowAutomation(Base):
    __tablename__ = "workflow_automation"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "version_id"], ["workflow_version.workspace_id", "workflow_version.id"]
        ),
        CheckConstraint("state IN ('active','paused','archived')", name="valid_automation_state"),
        CheckConstraint(BINDING, name="valid_automation_binding"),
        Index("ix_automation_due", "state", "kind", "next_due_at"),
        Index("ix_automation_workspace", "workspace_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace.id"))
    version_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(20), default="active")
    key_hash: Mapped[str | None] = mapped_column(String(64))
    interval_seconds: Mapped[int | None]
    cron_expression: Mapped[str | None] = mapped_column(String(100))
    timezone: Mapped[str | None] = mapped_column(String(64))
    input_nonce: Mapped[bytes | None] = mapped_column(LargeBinary)
    input_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
