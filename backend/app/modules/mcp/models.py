import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class McpConnection(Base):
    __tablename__ = "mcp_connection"
    __table_args__ = (
        UniqueConstraint("workspace_id", "server_id"),
        CheckConstraint("state IN ('active','revoked')", name="valid_mcp_state"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    server_id: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    verified_tools: Mapped[list] = mapped_column(JSONB, nullable=False)
    tool_snapshots: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
