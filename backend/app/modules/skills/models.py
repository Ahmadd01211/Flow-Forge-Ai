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


class Skill(Base):
    """Reusable know-how: instructions, examples and the tools they need, attached to agents."""

    __tablename__ = "skill"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint("revision >= 1", name="positive_revision"),
        Index("ix_skill_workspace_updated", "workspace_id", text("updated_at DESC")),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace.id"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(300), default="")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    revision: Mapped[int] = mapped_column(default=1)
    starter_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SkillVersion(Base):
    """An immutable published skill; agents pin one when they are published."""

    __tablename__ = "skill_version"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "skill_id"], ["skill.workspace_id", "skill.id"]),
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("skill_id", "number", name="uq_skill_version_number"),
        CheckConstraint("number >= 1 AND source_revision >= 1", name="positive_version"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column()
    skill_id: Mapped[uuid.UUID] = mapped_column()
    number: Mapped[int] = mapped_column()
    source_revision: Mapped[int] = mapped_column()
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(300))
    config: Mapped[dict] = mapped_column(JSONB)
    config_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
