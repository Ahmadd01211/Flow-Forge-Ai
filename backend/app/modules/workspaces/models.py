import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Workspace(Base):
    __tablename__ = "workspace"
    __table_args__ = (
        CheckConstraint("daily_budget_usd >= 0 AND daily_budget_usd <= 10000", name="workspace_daily_budget"),
        CheckConstraint("daily_run_limit BETWEEN 1 AND 10000", name="workspace_daily_run_limit"),
        CheckConstraint("active_run_limit BETWEEN 1 AND 4", name="workspace_active_run_limit"),
        CheckConstraint("quota_revision >= 1", name="workspace_quota_revision"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    daily_budget_usd: Mapped[Decimal] = mapped_column(Numeric(13, 8), default=Decimal("10"), server_default="10")
    daily_run_limit: Mapped[int] = mapped_column(default=1000, server_default="1000")
    active_run_limit: Mapped[int] = mapped_column(default=4, server_default="4")
    quota_revision: Mapped[int] = mapped_column(default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceMember(Base):
    __tablename__ = "workspace_member"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id"),
        CheckConstraint("role IN ('owner','admin','editor','viewer')", name="valid_role"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="owner")


class WorkspaceInvitation(Base):
    __tablename__ = "workspace_invitation"
    __table_args__ = (
        CheckConstraint("role IN ('admin','editor','viewer')", name="invitation_role"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace.id"), index=True)
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
